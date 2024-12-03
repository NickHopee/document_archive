import sqlite3
from datetime import datetime
import os
from typing import Optional, List, Dict
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

class DatabaseManager:
    def __init__(self, db_path: str = "archive.db"):
        self.db_path = db_path
        self._create_tables()
        self.check_database_structure()
        self.verify_document_table()

    def _create_tables(self):
        """Создание таблиц базы данных"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Таблица пользователей
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    password TEXT NOT NULL,
                    role TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Таблица папок
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS folders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    path TEXT UNIQUE NOT NULL,
                    parent_path TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Таблица документов
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS documents (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    description TEXT,
                    file_path TEXT,
                    folder_path TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    author TEXT NOT NULL,
                    tags TEXT,
                    cabinet TEXT,
                    shelf TEXT,
                    box TEXT,
                    FOREIGN KEY (folder_path) REFERENCES folders(path)
                )
            """)

            # Создание индексов
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_folders_path ON folders(path)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_documents_folder ON documents(folder_path)")

            # Добавление админа по умолчанию, если его нет
            cursor.execute("SELECT id FROM users WHERE username = 'admin'")
            if not cursor.fetchone():
                cursor.execute("""
                    INSERT INTO users (username, password, role)
                    VALUES (?, ?, ?)
                """, ("admin", "admin", "admin"))

            conn.commit()

    def get_user(self, username: str) -> Optional[Dict]:
        """Получение пользователя по имени"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT username, password, role
                FROM users
                WHERE username = ?
            """, (username,))
            row = cursor.fetchone()
            if row:
                return {
                    "username": row[0],
                    "password": row[1],
                    "role": row[2]
                }
            return None

    def get_folders(self) -> Dict[str, Dict]:
        """Получение всех папок"""
        print("Начало получения папок из БД")  # Отладка
        folders = {}
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT path, name, parent_path FROM folders")
                rows = cursor.fetchall()
                print(f"Получено записей из БД: {len(rows)}")  # Отладка
                
                for row in rows:
                    path, name, parent_path = row
                    print(f"Обработка папки: path={path}, name={name}, parent={parent_path}")  # Отладка
                    folders[path] = {
                        "name": name,
                        "parent_path": parent_path,
                        "subfolders": set()
                    }
                
                # Заполняем подпапки
                for path, folder in folders.items():
                    if parent_path := folder.get("parent_path"):
                        if parent_path in folders:
                            folders[parent_path]["subfolders"].add(path)
                
                print(f"Итоговая структура папок: {folders}")  # Отладка
                return folders
                
        except sqlite3.Error as e:
            print(f"Ошибка при получении папок из БД: {e}")  # Отладка
            return {}

    def add_folder(self, name: str, path: str, parent_path: Optional[str] = None) -> bool:
        """Добавление новой папки"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO folders (name, path, parent_path)
                    VALUES (?, ?, ?)
                """, (name, path, parent_path))
                conn.commit()
                return True
        except sqlite3.IntegrityError:
            return False

    def rename_folder(self, old_path: str, new_name: str, new_path: str) -> bool:
        """Переименование папки"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                # Обновляем имя и путь папки
                cursor.execute("""
                    UPDATE folders 
                    SET name = ?, path = ?
                    WHERE path = ?
                """, (new_name, new_path, old_path))
                
                # Обновляем пути в дочерних папках
                cursor.execute("""
                    UPDATE folders
                    SET path = replace(path, ?, ?),
                        parent_path = replace(parent_path, ?, ?)
                    WHERE path LIKE ?
                """, (old_path, new_path, old_path, new_path, f"{old_path}/%"))
                
                # Обновляем пути в документах
                cursor.execute("""
                    UPDATE documents
                    SET folder_path = replace(folder_path, ?, ?)
                    WHERE folder_path LIKE ?
                """, (old_path, new_path, f"{old_path}%"))
                
                conn.commit()
                return True
        except sqlite3.Error:
            return False

    def delete_folder(self, path: str) -> bool:
        """Удаление папки"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                # Проверяем наличие документов
                cursor.execute("SELECT COUNT(*) FROM documents WHERE folder_path = ?", (path,))
                if cursor.fetchone()[0] > 0:
                    return False
                
                # Проверяем наличие подпапок
                cursor.execute("SELECT COUNT(*) FROM folders WHERE parent_path = ?", (path,))
                if cursor.fetchone()[0] > 0:
                    return False
                
                # Удаляем папку
                cursor.execute("DELETE FROM folders WHERE path = ?", (path,))
                conn.commit()
                return True
        except sqlite3.Error:
            return False

    def get_documents(self, folder_path: str) -> List[Dict]:
        """Получение документов в папке"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                query = """
                    SELECT id, title, description, file_path, status, created_date, 
                           author, tags, cabinet, shelf, box
                    FROM documents
                    WHERE folder_path = ?
                    ORDER BY created_date DESC
                """
                cursor.execute(query, (folder_path,))
                
                documents = []
                for row in cursor.fetchall():
                    doc = {
                        "id": row[0],
                        "title": row[1],
                        "description": row[2],
                        "file_path": row[3],
                        "status": row[4],
                        "date_added": row[5],
                        "author": row[6],
                        "tags": row[7].split(',') if row[7] else [],
                        "cabinet": row[8],
                        "shelf": row[9],
                        "box": row[10]
                    }
                    documents.append(doc)
                return documents
        except sqlite3.Error as e:
            print(f"Ошибка при получении документов: {e}")
            return []

    def add_document(self, title: str, description: str, file_path: str, 
                    folder_path: str, status: str, author: str, 
                    cabinet: str = None, shelf: str = None, box: str = None,
                    tags: List[str] = None) -> bool:
        """Добавление нового документа"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                query = """
                    INSERT INTO documents 
                    (title, description, file_path, folder_path, status, author, 
                     cabinet, shelf, box, tags)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """
                params = (
                    title, description, file_path, folder_path, status, author,
                    cabinet, shelf, box,
                    ','.join(tags) if tags else None
                )
                cursor.execute(query, params)
                conn.commit()
                return True
        except sqlite3.Error as e:
            print(f"Ошибка при добавлении документа: {e}")
            return False

    def delete_document(self, document_id: int) -> bool:
        """Удаление документа"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                # Получаем путь к файлу перед удалением
                cursor.execute("SELECT file_path FROM documents WHERE id = ?", (document_id,))
                result = cursor.fetchone()
                if result:
                    file_path = result[0]
                    # Удаляем запись из БД
                    cursor.execute("DELETE FROM documents WHERE id = ?", (document_id,))
                    conn.commit()
                    # Удаляем файл, если он существует
                    if file_path and os.path.exists(file_path):
                        os.remove(file_path)
                    return True
            return False
        except sqlite3.Error as e:
            logger.error(f"Ошибка при удалении документа: {e}")
            return False

    def check_database_structure(self):
        """Проверка структуры базы данных"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Проверяем таблицу documents
                cursor.execute("PRAGMA table_info(documents)")
                columns = cursor.fetchall()
                print("\nСтруктура таблицы documents:")
                for col in columns:
                    print(f"Колонка: {col}")
                
                # Проверяем наличие данных
                cursor.execute("SELECT COUNT(*) FROM documents")
                count = cursor.fetchone()[0]
                print(f"\nКоличество документов в базе: {count}")
                
                if count > 0:
                    cursor.execute("SELECT * FROM documents LIMIT 1")
                    doc = cursor.fetchone()
                    print(f"Пример документа: {doc}")
                    
        except sqlite3.Error as e:
            print(f"Ошибка при проверке структуры БД: {e}") 

    def verify_document_table(self):
        """Проверка таблицы документов"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Пробуем добавить тестовый документ
                cursor.execute("""
                    INSERT INTO documents 
                    (title, description, file_path, folder_path, status, author)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, ("Тест", "Тестовый документ", "/test/path", "/", "Активный", "admin"))
                
                doc_id = cursor.lastrowid
                print(f"Тестовый документ создан с ID: {doc_id}")
                
                # Проверяем, что документ добавился
                cursor.execute("SELECT * FROM documents WHERE id = ?", (doc_id,))
                doc = cursor.fetchone()
                print(f"Тестовый документ в БД: {doc}")
                
                # Удаляем тестовый документ
                cursor.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
                conn.commit()
                
                return True
        except sqlite3.Error as e:
            print(f"Ошибка при проверке таблицы documents: {e}")
            return False

    def get_folder_name(self, folder_path: str) -> str:
        """Получение имени папки по её пути"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT name FROM folders WHERE path = ?",
                    (folder_path,)
                )
                result = cursor.fetchone()
                return result[0] if result else "Корневая папка" if folder_path == "/" else "Неизвестная папка"
        except sqlite3.Error as e:
            print(f"Ошибка при получении имени папки: {e}")
            return "Ошибка"

    def get_subfolders(self, parent_path: str) -> List[str]:
        """Получение списка подпапок для указанной папки"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Если это корневая папка
                if parent_path == "/":
                    query = "SELECT path FROM folders WHERE path != '/' AND path NOT LIKE '%/%/%'"
                    cursor.execute(query)
                else:
                    # Для остальных папок ищем прямых потомков
                    query = """
                        SELECT path FROM folders 
                        WHERE path LIKE ? 
                        AND path != ? 
                        AND (
                            LENGTH(path) - LENGTH(REPLACE(path, '/', '')) = 
                            LENGTH(?) - LENGTH(REPLACE(?, '/', '')) + 1
                        )
                    """
                    parent_path_pattern = f"{parent_path}/%"
                    cursor.execute(query, (parent_path_pattern, parent_path, parent_path, parent_path))
                
                result = cursor.fetchall()
                return [row[0] for row in result]
                
        except sqlite3.Error as e:
            print(f"Ошибка при получении подпапок: {e}")
            return []

    def has_subfolders(self, folder_path: str) -> bool:
        """Проверка наличия подпапок"""
        return bool(self.get_subfolders(folder_path))

    def has_documents(self, folder_path: str) -> bool:
        """Проверка наличия документов в папке"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT COUNT(*) FROM documents WHERE folder_path = ?", 
                    (folder_path,)
                )
                return cursor.fetchone()[0] > 0
        except sqlite3.Error as e:
            print(f"Ошибка при проверке документов: {e}")
            return False 

    def update_document(self, doc_id: int, **fields) -> bool:
        """Обновление документа"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                update_fields = []
                values = []
                for field, value in fields.items():
                    if value is not None:  # Обновляем только непустые поля
                        update_fields.append(f"{field} = ?")
                        values.append(value)
                
                if not update_fields:
                    return False
                    
                values.append(doc_id)  # Добавляем id для WHERE условия
                
                query = f"""
                    UPDATE documents 
                    SET {', '.join(update_fields)}
                    WHERE id = ?
                """
                
                cursor.execute(query, values)
                conn.commit()
                return True
                
        except sqlite3.Error as e:
            print(f"Ошибка при обновлении документа: {e}")
            return False

    def get_document(self, doc_id: int) -> Dict:
        """Получение документа по id"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT * FROM documents WHERE id = ?",
                    (doc_id,)
                )
                row = cursor.fetchone()
                if row:
                    column_names = [description[0] for description in cursor.description]
                    return dict(zip(column_names, row))
                return None
        except sqlite3.Error as e:
            print(f"Ошибка при получении документа: {e}")
            return None 

    def search_documents(self, query: str, folder_path: Optional[str] = None) -> List[Dict]:
        """Поиск документов по заданному запросу"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Базовый SQL запрос
                sql = """
                    SELECT * FROM documents 
                    WHERE (
                        title LIKE ? OR 
                        description LIKE ? OR 
                        status LIKE ? OR 
                        author LIKE ? OR 
                        tags LIKE ? OR
                        cabinet LIKE ? OR
                        shelf LIKE ? OR
                        box LIKE ?
                    )
                """
                
                # Если указана папка, добавляем условие
                if folder_path:
                    sql += " AND folder_path = ?"
                    params = [f"%{query}%"] * 8 + [folder_path]
                else:
                    params = [f"%{query}%"] * 8
                
                cursor.execute(sql, params)
                
                # Преобразуем результаты в словари
                columns = [description[0] for description in cursor.description]
                return [dict(zip(columns, row)) for row in cursor.fetchall()]
                
        except sqlite3.Error as e:
            print(f"Ошибка при поиске документов: {e}")
            return []

    def get_all_users(self) -> List[Dict]:
        """Получение списка всех пользователей"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT username, role FROM users")
                return [{"username": row[0], "role": row[1]} for row in cursor.fetchall()]
        except sqlite3.Error as e:
            print(f"Ошибка при получении списка пользователей: {e}")
            return []

    def add_user(self, username: str, password: str, role: str) -> bool:
        """Добавление нового пользователя"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT INTO users (username, password, role) VALUES (?, ?, ?)",
                    (username, password, role)
                )
                conn.commit()
                return True
        except sqlite3.Error as e:
            print(f"Ошибка при добавлении пользователя: {e}")
            return False

    def delete_user(self, username: str) -> bool:
        """Удаление пользователя"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM users WHERE username = ? AND username != 'admin'", (username,))
                conn.commit()
                return True
        except sqlite3.Error as e:
            print(f"Ошибка при удалении пользователя: {e}")
            return False

    def get_documents_count(self) -> int:
        """Получение общего количества документов"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM documents")
                return cursor.fetchone()[0]
        except sqlite3.Error as e:
            print(f"Ошибка при подсчете документов: {e}")
            return 0

    def get_folders_count(self) -> int:
        """Получение общего количества папок"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM folders")
                return cursor.fetchone()[0]
        except sqlite3.Error as e:
            print(f"Ошибка при подсчете папок: {e}")
            return 0

    def get_users_count(self) -> int:
        """Получение общего количества пользователей"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM users")
                return cursor.fetchone()[0]
        except sqlite3.Error as e:
            print(f"Ошибка при подсчете пользователей: {e}")
            return 0