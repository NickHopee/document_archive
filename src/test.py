import flet as ft
from datetime import datetime
import os
from typing import Optional, Dict, List
from dataclasses import dataclass
from pathlib import Path
import fitz 
import tempfile
from PIL import Image
import io
from database import DatabaseManager

@dataclass
class Document:
    """Класс для представления документа"""
    def __init__(self, title, file_path, status, created_date, author):
        self.name = title  # Явно задаем атрибут name
        self.title = title
        self.file_path = file_path
        self.status = status
        self.created_date = created_date
        self.author = author
        self.version = 1
        self.history = []

@dataclass
class User:
    username: str
    role: str
    password: str
    
    @property
    def is_admin(self) -> bool:
        return self.role == "admin"
    
    @property
    def is_editor(self) -> bool:
        return self.role in ["admin", "editor"]
    
    @property
    def can_delete(self) -> bool:
        return self.role in ["admin", "editor"]
    
    @property
    def can_edit(self) -> bool:
        return self.role in ["admin", "editor"]
    
    @property
    def can_create(self) -> bool:
        return self.role in ["admin", "editor"]
    
    @property
    def can_create_root_folder(self) -> bool:
        """Может ли пользователь создавать корневые папки"""
        return self.role == "admin"  # Только админ может создавать корневые папки

class FolderTree:
    def __init__(self, app):
        self.app = app
        self.expanded_paths = set()

    def build_tree(self) -> List[ft.Control]:
        """Построение дерева папок"""
        print(f"Текущие папки в build_tree: {self.app.folders}")  # Отладка
        tree_controls = []
        
        # Изменяем логику определения корневых папок
        root_folders = {
            path: folder for path, folder in self.app.folders.items()
            if not folder.get("parent_path")  # Используем parent_path вместо проверки путей
        }
        
        print(f"Найденные корневые папки: {root_folders}")  # Отладка
        
        # Сортируем корневые папки по имени
        sorted_root_paths = sorted(root_folders.keys(), key=lambda x: self.app.folders[x]["name"])
        
        # Строим дерево для каждой корневой папки
        for path in sorted_root_paths:
            tree_controls.append(self.create_folder_item(
                self.app.folders[path]["name"],
                path,
                is_root=True
            ))
            
            # Если папка развернута, добавляем её подпапки
            if path in self.expanded_paths:
                tree_controls.extend(self._build_subtree(path))
        
        print(f"Количество элементов в дереве: {len(tree_controls)}")  # Отладка
        return tree_controls

    def _build_subtree(self, parent_path: str, level: int = 1) -> List[ft.Control]:
        """Построение поддерева для заданной папки"""
        subtree_controls = []
        
        # Получаем все прямые подпапки текущей папки
        subfolders = {
            path: folder for path, folder in self.app.folders.items()
            if folder.get("parent_path") == parent_path  # Используем parent_path
        }
        
        # Сортируем подпапки по имени
        sorted_subfolder_paths = sorted(subfolders.keys(), 
                                      key=lambda x: self.app.folders[x]["name"])
        
        # Добавляем каждую подпапку
        for path in sorted_subfolder_paths:
            subtree_controls.append(
                self.create_folder_item(
                    self.app.folders[path]["name"],
                    path,
                    level=level
                )
            )
            
            # Если папка развернута, рекурсивно добавляем её подпапки
            if path in self.expanded_paths:
                subtree_controls.extend(self._build_subtree(path, level + 1))
        
        return subtree_controls

    def create_folder_item(self, name: str, path: str, is_root: bool = False, level: int = 0) -> ft.Container:
        """Создание элемента папки с выделением"""
        is_expanded = path in self.expanded_paths
        is_selected = path == self.app.current_folder
        has_subfolders = bool(self.app.folders[path]["subfolders"])
        
        def toggle_expand(e):
            if path in self.expanded_paths:
                self.expanded_paths.remove(path)
            else:
                self.expanded_paths.add(path)
            self.app.update_folder_tree()
            
        def show_folder_menu(e):
            self.app.show_folder_menu(e, path)

        # Настройки текста
        text_size = 16 if is_root else 14
        text_weight = ft.FontWeight.BOLD if is_root or is_selected else ft.FontWeight.NORMAL
        text_color = ft.colors.WHITE if is_selected else None

        # Настройки иконок
        icon_color = ft.colors.WHITE if is_selected else (ft.colors.BLUE if is_root else ft.colors.GREY_700)

        # Расчет отступов
        base_indent = 8
        level_indent = 16
        total_indent = level * level_indent + base_indent

        folder_row = ft.Row(
            [
                ft.Container(width=total_indent),
                ft.IconButton(
                    icon=ft.icons.EXPAND_MORE if is_expanded else ft.icons.CHEVRON_RIGHT,
                    on_click=toggle_expand,
                    icon_size=16,
                    icon_color=icon_color,
                    visible=has_subfolders,
                    style=ft.ButtonStyle(
                        padding=ft.padding.all(0),
                    ),
                ),
                ft.Icon(
                    name=ft.icons.FOLDER_OPEN if is_expanded else ft.icons.FOLDER,
                    size=16,
                    color=icon_color,
                ),
                ft.Text(
                    name,
                    size=text_size,
                    color=text_color,
                    weight=text_weight,
                ),
                ft.IconButton(
                    icon=ft.icons.MORE_VERT,
                    icon_size=16,
                    icon_color=icon_color,
                    on_click=show_folder_menu,
                    style=ft.ButtonStyle(
                        padding=ft.padding.all(0),
                    ),
                ),
            ],
            spacing=4,
            alignment=ft.MainAxisAlignment.START,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

        return ft.Container(
            content=folder_row,
            data=path,
            bgcolor=ft.colors.BLUE_700 if is_selected else None,
            border_radius=5,
            padding=ft.padding.only(left=0, top=5, right=10, bottom=5),
            ink=True,
            on_click=lambda e: self.app.select_folder(path),
        )

class ArchiveApp:
    def __init__(self):
        self.db = DatabaseManager()
        self.current_user = None
        self.current_folder = None
        self.folder_tree = None
        self.preview_panel = None
        self.current_document = None
        self.folders = {}
        self.documents = {}
        
        # Добавляем атрибуты для работы с файлами
        self.selected_file_path = None
        self.file_path_field = None
        self.title_field = None
        self.description_field = None
        self.status_dropdown = None
        self.cabinet_field = None
        self.shelf_field = None
        self.box_field = None
        
        self.supported_previews = {
            ".txt": self.text_preview,
            ".pdf": self.pdf_preview,
            ".jpg": self.image_preview,
            ".jpeg": self.image_preview,
            ".png": self.image_preview,
            ".docx": self.docx_preview,
        }

        # Добавляем атрибут для хранения путей к временным файлам
        self.temp_files = set()

    def authenticate(self, username: str, password: str) -> bool:
        """Аутентификация пользователя"""
        print("Начало аутентификации")  # Отладка
        user_data = self.db.get_user(username)
        if user_data and user_data["password"] == password:
            self.current_user = User(
                username=user_data["username"],
                password=user_data["password"],
                role=user_data["role"]
            )
            # Загружаем папки после успешной авторизации
            self.folders = self.db.get_folders()
            print(f"Папки после авторизации: {self.folders}")  # Отладка
            return True
        return False

    def show_error(self, message: str):
        """Показ сообщения об ошибке"""
        if hasattr(self, 'page'):
            self.page.show_snack_bar(
                ft.SnackBar(content=ft.Text(message), bgcolor=ft.colors.ERROR)
            )

    def show_login_dialog(self):
        """Показ диалога входа"""
        def try_login(e):
            username = username_field.value
            password = password_field.value
            if self.authenticate(username, password):
                dialog.open = False
                self.page.update()
                self.create_main_ui()
            else:
                self.show_error("Неверное имя пользователя или пароль")

        username_field = ft.TextField(label="Имя пользователя")
        password_field = ft.TextField(label="Пароль", password=True)
        
        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("Вход в систему"),
            content=ft.Column([username_field, password_field]),
            actions=[ft.TextButton("Войти", on_click=try_login)]
        )
        
        self.page.overlay.append(dialog)
        dialog.open = True
        self.page.update()

    def create_main_ui(self):
        """Создание основного интерфейса с учетом прав пользователя"""
        print("Создание основного интерфейса")  # Отладка
        # Загружаем папки при создании интерфейса
        self.folders = self.db.get_folders()
        print(f"Папки при создании интерфейса: {self.folders}")  # Отладка
        
        # Создаем компоненты интерфейса
        self.folder_list = ft.ListView(expand=1, spacing=0, padding=10)
        self.folder_tree = FolderTree(self)
        
        # Кнопка создания корневой папки только для админов
        create_root_folder_button = ft.ElevatedButton(
            "Создать корневую папку",
            icon=ft.icons.CREATE_NEW_FOLDER_OUTLINED,
            on_click=lambda _: self.add_root_folder_dialog(),
            visible=self.current_user.can_create_root_folder
        )
        
        # Создаем левую панель с деревом папок
        left_panel = ft.Container(
            content=ft.Column([
                create_root_folder_button,  # Кнопка создания корневой папки
                ft.Divider(),
                self.folder_list  # Добавляем список папок в контейнер
            ]),
            width=300,
            padding=10
        )

        # Создаем центральную панель
        self.document_list = ft.ListView(expand=1, spacing=2, padding=10)
        center_panel = ft.Container(
            content=ft.Column([
                ft.Row([
                    ft.Text("Документы", size=20, weight=ft.FontWeight.BOLD),
                    ft.IconButton(
                        icon=ft.icons.ADD,
                        tooltip="Добавить документ",
                        on_click=lambda _: self.add_document_dialog()
                    )
                ]),
                self.create_search_bar(),
                ft.Divider(),
                self.document_list
            ]),
            expand=True,
            padding=10,
            width=400
        )

        # Создаем правую панель
        self.preview_panel = ft.Container(
            content=ft.Column(
                controls=[
                    ft.Container(
                        content=ft.Text(
                            "Выберите документ для просмотра",
                            color=ft.colors.GREY_500,
                            text_align=ft.TextAlign.CENTER
                        ),
                        alignment=ft.alignment.center,
                    )
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            width=500,
            bgcolor=ft.colors.BACKGROUND,
            border=ft.border.all(1, ft.colors.OUTLINE),
            border_radius=10,
            padding=20
        )

        # Добавляем все компоненты на страницу
        self.page.add(
            ft.Column(
                [
                    # Верхняя панель
                    ft.Container(
                        content=ft.Row(
                            [
                                ft.Text(
                                    f"Пользователь: {self.current_user.username}",
                                    size=14,
                                    weight=ft.FontWeight.BOLD
                                ),
                                ft.IconButton(
                                    icon=ft.icons.LOGOUT,
                                    tooltip="Выйти",
                                    on_click=lambda _: self.logout()
                                ),
                                ft.IconButton(
                                    icon=ft.icons.ADMIN_PANEL_SETTINGS,
                                    tooltip="Панель администратора",
                                    on_click=lambda _: self.show_admin_panel(),
                                    visible=self.current_user.is_admin
                                )
                            ],
                            alignment=ft.MainAxisAlignment.END
                        ),
                        padding=10
                    ),
                    # Основные панели
                    ft.Row(
                        [
                            left_panel,
                            ft.VerticalDivider(),
                            center_panel,
                            ft.VerticalDivider(),
                            self.preview_panel
                        ],
                        expand=True
                    )
                ],
                expand=True
            )
        )

        # После добавления всех компонентов на страницу обновляем дерево папок
        self.update_folder_tree()
        self.page.update()

    def show_preview(self, doc: Dict):
        """Показать превью документа"""
        try:
            print(f"Показываем превью для документа: {doc}")
            
            # Создаем информацию о расположении
            location_parts = []
            if doc.get("cabinet"):
                location_parts.append(f"Шкаф: {doc['cabinet']}")
            if doc.get("shelf"):
                location_parts.append(f"Полка: {doc['shelf']}")
            if doc.get("box"):
                location_parts.append(f"Короб: {doc['box']}")
            
            location_text = " | ".join(location_parts) if location_parts else "Расположение не указано"

            # Создаем заголовок с информацией о документе
            header = ft.Column(
                controls=[
                    ft.Text(
                        doc.get("title", "Без названия"),
                        size=20,
                        weight=ft.FontWeight.BOLD
                    ),
                    ft.Text(
                        doc.get("description", "Описание отсутствует"),
                        size=14,
                        color=ft.colors.GREY_700
                    ),
                    ft.Row(
                        controls=[
                            ft.Text(
                                f"Статус: {doc.get('status', 'Не указан')}",
                                size=12,
                                color=ft.colors.GREY_600
                            ),
                            ft.Text("•", size=12, color=ft.colors.GREY_400),
                            ft.Text(
                                f"Добавлено: {doc.get('date_added', 'Дата не указана')}",
                                size=12,
                                color=ft.colors.GREY_600
                            ),
                            ft.Text("•", size=12, color=ft.colors.GREY_400),
                            ft.Text(
                                f"Автор: {doc.get('author', 'Автор не указан')}",
                                size=12,
                                color=ft.colors.GREY_600
                            )
                        ],
                        spacing=10
                    ),
                    ft.Text(
                        location_text,
                        size=12,
                        color=ft.colors.GREY_700
                    )
                ],
                spacing=10
            )

            # Создаем кнопки действий
            actions = ft.Row(
                controls=[
                    ft.IconButton(
                        icon=ft.icons.DOWNLOAD,
                        tooltip="Скачать",
                        on_click=lambda e, doc=doc: self.download_document(doc)
                    ),
                    ft.IconButton(
                        icon=ft.icons.EDIT,
                        tooltip="Редактировать",
                        on_click=lambda e, doc=doc: self.edit_document(doc)
                    ),
                    ft.IconButton(
                        icon=ft.icons.DELETE,
                        tooltip="Удалить",
                        on_click=lambda e, doc=doc: self.delete_document(doc)
                    ),
                ]
            )

            # Создаем превью файла
            preview = ft.Container(
                content=ft.Text("Предпросмотр документа недоступен"),
                alignment=ft.alignment.center,
                bgcolor=ft.colors.GREY_100,
                border_radius=10,
                padding=20,
                height=400
            )

            # Пытаемся создать превью в зависимости от типа файла
            file_path = doc.get("file_path", "")
            if file_path:
                file_ext = Path(file_path).suffix.lower()
                if file_ext in self.supported_previews:
                    preview = self.supported_previews[file_ext](file_path)

            # Собираем все элементы вместе
            content = ft.Column(
                controls=[
                    header,
                    ft.Divider(),
                    preview,
                    ft.Divider(),
                    actions
                ],
                spacing=20
            )

            # Показываем диалог
            dialog = ft.AlertDialog(
                modal=True,
                title=ft.Text("Просмотр документа"),
                content=content,
                actions=[
                    ft.TextButton("Закрыть", on_click=lambda e: self.close_preview(dialog))
                ],
                actions_alignment=ft.MainAxisAlignment.END
            )

            self.page.overlay.append(dialog)
            dialog.open = True
            self.page.update()

        except Exception as e:
            print(f"Ошибка при показе превью: {e}")
            self.show_error("Ошибка при показе превью документа")

    def close_preview(self, dialog):
        """Закрыть превью документа"""
        dialog.open = False
        self.page.update()
        self.cleanup_temp_files()  # Очищаем временные файлы при закрытии превью

    def text_preview(self, file_path: str) -> ft.Container:
        """Превью текстового документа"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read(1000)  # Читаем первые 1000 символов
            return ft.Container(
                content=ft.Text(content + "..." if len(content) == 1000 else content),
                bgcolor=ft.colors.SURFACE_VARIANT,
                border_radius=5,
                padding=10,
                height=400
            )
        except Exception as e:
            return ft.Container(
                content=ft.Text("Ошибка чтения файла", color=ft.colors.ERROR),
                height=400
            )

    def image_preview(self, file_path: str) -> ft.Container:
        """Превью изображения"""
        return ft.Container(
            content=ft.Image(
                src=file_path,
                fit=ft.ImageFit.CONTAIN,
                border_radius=5,
            ),
            height=400
        )

    def pdf_preview(self, file_path: str) -> ft.Container:
        """Превью PDF"""
        try:
            import fitz  # PyMuPDF
            import tempfile
            import os
            
            # Открываем PDF
            pdf_document = fitz.open(file_path)
            
            if len(pdf_document) > 0:
                # Берем первую страницу
                page = pdf_document[0]
                # Получаем изображение страницы
                pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))  # Масштаб 2x для лучшего качества
                
                # Создаем временный файл с уникальным именем
                temp_dir = tempfile.gettempdir()
                temp_file = os.path.join(temp_dir, f"preview_{os.getpid()}_{id(self)}.png")
                
                # Сохраняем изображение
                pix.save(temp_file)
                
                # Закрываем PDF
                pdf_document.close()
                    
                # Возвращаем контейнер с изображением и кнопкой
                return ft.Container(
                    content=ft.Column(
                        controls=[
                            ft.Image(
                                src=temp_file,
                                fit=ft.ImageFit.CONTAIN,
                                border_radius=5,
                                height=350,
                            ),
                            ft.ElevatedButton(
                                "Открыть PDF полностью",
                                icon=ft.icons.PICTURE_AS_PDF,
                                on_click=lambda e: self.open_document(file_path)
                            )
                        ],
                        alignment=ft.MainAxisAlignment.CENTER,
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                        spacing=10
                    ),
                    height=400,
                    alignment=ft.alignment.center
                )
                    
        except Exception as e:
            print(f"Ошибка при создании превью PDF: {e}")
            if 'pdf_document' in locals():
                pdf_document.close()
        
        # Если что-то пошло не так, показываем запасной вариант
        return ft.Container(
            content=ft.Column(
                controls=[
                    ft.Text("Ошибка при создании превью PDF"),
                    ft.ElevatedButton(
                        "Открыть в программе просмотра",
                        icon=ft.icons.PICTURE_AS_PDF,
                        on_click=lambda e: self.open_document(file_path)
                    )
                ],
                alignment=ft.MainAxisAlignment.CENTER,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER
            ),
            height=400,
            alignment=ft.alignment.center
        )

    def docx_preview(self, file_path: str) -> ft.Container:
        """Превью DOCX"""
        return ft.Container(
            content=ft.Column(
                controls=[
                    ft.Text("Предпросмотр DOCX временно недоступен"),
                    ft.ElevatedButton(
                        "Открыть в программе просмотра",
                        icon=ft.icons.DESCRIPTION,
                        on_click=lambda e: self.open_document(file_path)
                    )
                ],
                alignment=ft.MainAxisAlignment.CENTER,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER
            ),
            height=400,
            alignment=ft.alignment.center
        )

    def open_document(self, file_path: str):
        """Открытие документа в системном приложении"""
        try:
            import os
            if os.path.exists(file_path):
                os.startfile(file_path)
            else:
                self.show_error("Файл не найден")
        except Exception as e:
            self.show_error(f"Ошибка при открытии файла: {str(e)}")

    def add_search_bar(self):
        """Добавление поиска"""
        def on_search_change(e):
            search_term = search_field.value.lower()
            self.filter_documents(search_term)
        
        search_field = ft.TextField(
            label="Поиск документов",
            prefix_icon=ft.icons.SEARCH,
            on_change=on_search_change,
            width=300
        )
        return search_field

    def filter_documents(self, search_term: str):
        """Фильтрация документов"""
        if not search_term:
            self.update_documents_list()
            return
        
        search_term = search_term.lower()
        self.document_list.controls.clear()
        current_docs = self.documents.get(self.current_folder, [])
        
        for doc in current_docs:
            if (search_term in doc.title.lower() or 
                search_term in doc.description.lower() or
                any(search_term in tag.lower() for tag in (doc.tags or []))):
                self.document_list.controls.append(
                    self.create_document_card(doc)
                )
        self.document_list.update()

    def create_pdf_preview(self, pdf_path: str) -> Optional[str]:
        """Создание превью для PDF файла"""
        try:
            print(f"Создаем превью для PDF: {pdf_path}")
            
            # Проверяем расширение файла
            if not pdf_path.lower().endswith('.pdf'):
                print("Файл не является PDF")
                return None
            
            # Создаем временный файл для превью
            preview_path = f"temp_preview_{os.path.basename(pdf_path)}.png"
            print(f"Путь для сохранения превью: {preview_path}")
            
            # Конвертируем первую страницу PDF в изображение
            doc = fitz.open(pdf_path)
            page = doc[0]
            pix = page.get_pixmap()
            pix.save(preview_path)
            doc.close()
            
            print(f"Превью создано успешно: {preview_path}")
            return preview_path
            
        except Exception as e:
            print(f"Ошибка при создании превью PDF: {e}")
            return None

    def show_pdf_preview(self, pdf_path: str):
        """Показ превью PDF в правой панели"""
        try:
            # Показываем индикатор загрузки
            self.preview_panel.content.controls.clear()
            self.preview_panel.content.controls.extend([
                ft.Text("Загрузка превью...", size=16),
                ft.ProgressRing(),
            ])
            self.preview_panel.update()
            
            preview_path = self.create_pdf_preview(pdf_path)
            print(f"Создан путь для превью: {preview_path}")
            
            if preview_path:
                self.preview_panel.content.controls.clear()
                self.preview_panel.content.controls.extend([
                    ft.Text("Предпросмотр документа", size=16, weight=ft.FontWeight.BOLD),
                    ft.Image(
                        src=preview_path,
                        width=400,
                        height=500,
                        fit=ft.ImageFit.CONTAIN
                    ),
                    ft.ElevatedButton(
                        "Открыть документ",
                        icon=ft.icons.FILE_OPEN,
                        on_click=lambda e: self.open_pdf(pdf_path)
                    )
                ])
            else:
                self.preview_panel.content.controls.clear()
                self.preview_panel.content.controls.extend([
                    ft.Text("Не удалось создать превью", 
                           size=16, 
                           color=ft.colors.RED_400),
                    ft.Text("Попробуйте открыть документ напрямую"),
                    ft.ElevatedButton(
                        "Открыть документ",
                        icon=ft.icons.FILE_OPEN,
                        on_click=lambda e: self.open_pdf(pdf_path)
                    )
                ])
            self.preview_panel.update()
            
        except Exception as e:
            print(f"Ошибка при создании превью: {e}")
            self.show_error(f"Ошибка при создании превью: {str(e)}")

    def open_pdf(self, pdf_path: str):
        """Открытие PDF файла"""
        if os.path.exists(pdf_path):
            import webbrowser
            webbrowser.open(pdf_path)
        else:
            self.show_error("Файл не найден")

    def create_document_card(self, doc: dict):
        """Обновленная карточка документа с информацией о расположении"""
        # Формируем текст о расположении
        location_text = "Расположение: "
        location_parts = []
        
        if doc.get("cabinet"):
            location_parts.append(f"Кабинет {doc['cabinet']}")
        if doc.get("shelf"):
            location_parts.append(f"Полка {doc['shelf']}")
        if doc.get("box"):
            location_parts.append(f"Ящик {doc['box']}")
        
        location_text += " / ".join(location_parts) if location_parts else "Не указано"

        # Добавляем иконку в зависимости от типа файла
        file_path = doc.get('file_path', '')
        file_icon = ft.icons.DESCRIPTION
        if file_path.lower().endswith('.pdf'):
            file_icon = ft.icons.PICTURE_AS_PDF
        elif file_path.lower().endswith(('.jpg', '.jpeg', '.png')):
            file_icon = ft.icons.IMAGE
        elif file_path.lower().endswith(('.doc', '.docx')):
            file_icon = ft.icons.ARTICLE

        return ft.Container(
            content=ft.Row([
                ft.Icon(file_icon, size=40, color=ft.colors.BLUE_400),
                ft.Column([
                    ft.Text(doc.get('title', ''), 
                           size=16, 
                           weight=ft.FontWeight.BOLD),
                    ft.Text(doc.get('description', ''),
                           size=12,
                           color=ft.colors.GREY_700),
                    ft.Text(location_text, 
                           size=12, 
                           color=ft.colors.GREY_700),
                    ft.Row([
                        ft.Text(f"Статус: {doc.get('status', '')}",
                               size=12,
                               color=ft.colors.GREY_700),
                        ft.Text(f"Добавлено: {doc.get('date_added', '')}",
                               size=12,
                               color=ft.colors.GREY_700),
                    ]),
                    ft.Row([
                        ft.IconButton(
                            icon=ft.icons.PREVIEW,
                            icon_color=ft.colors.BLUE_400,
                            tooltip="Предпросмотр",
                            on_click=lambda e, doc=doc: self.show_pdf_preview(doc.get('file_path', ''))
                        ),
                        ft.IconButton(
                            icon=ft.icons.FILE_OPEN,
                            icon_color=ft.colors.GREEN_400,
                            tooltip="Открыть",
                            on_click=lambda e, doc=doc: self.open_pdf(doc.get('file_path', ''))
                        ),
                        ft.IconButton(
                            icon=ft.icons.DELETE,
                            icon_color=ft.colors.RED_400,
                            tooltip="Удалить",
                            on_click=lambda e, doc=doc: self.delete_document(doc)
                        ),
                    ])
                ], spacing=5, expand=True),
            ], alignment=ft.MainAxisAlignment.START),
            padding=10,
            border=ft.border.all(1, ft.colors.GREY_300),
            border_radius=10,
            ink=True,
            on_hover=lambda e: self.highlight_card(e)
        )

    def highlight_card(self, e):
        """Подсветка карточки при наведении"""
        if e.data == "true":  # мышь наведена
            e.control.bgcolor = ft.colors.BLUE_GREY_50
        else:  # мышь убрана
            e.control.bgcolor = None
        e.control.update()

    async def add_document(self, e):
        """Добавление документа с асинхронной обработкой"""
        print("Начало добавления документа")  # Отладочный вывод
        
        if not self._validate_document_input():
            return

        try:
            # Создаем директорию для файлов, если её нет
            files_dir = Path("document_files")
            files_dir.mkdir(exist_ok=True)

            # Получаем имя исходного файла и создаем путь для нового файла
            source_file_path = Path(self.selected_file_path)
            new_file_path = files_dir / source_file_path.name
            
            print(f"Копирование файла из {self.selected_file_path} в {new_file_path}")
            
            # Копируем файл
            import shutil
            shutil.copy2(self.selected_file_path, new_file_path)
            
            # Создаем процессор документов
            processor = DocumentProcessor()
            
            # Асинхронная обработка документа
            processing_result = await processor.process_document(str(new_file_path))
            
            print("Добавление документа в БД")  # Отладочный вывод
            
            # Добавляем документ в БД с дополнительными данными
            success = self.db.add_document(
                title=self.title_field.value,
                description=self.description_field.value,
                file_path=str(new_file_path),
                folder_path=self.current_folder,
                status=self.status_dropdown.value,
                author=self.current_user.username,
                cabinet=self.cabinet_field.value,
                shelf=self.shelf_field.value,
                box=self.box_field.value,
                tags=[]
            )
            
            if success:
                print("Документ успешно добавлен")
                # Закрываем диалог
                for dlg in self.page.overlay:
                    if isinstance(dlg, ft.AlertDialog):
                        dlg.open = False
                self.page.update()
                self.update_documents_list()
                self.show_snack_bar("Документ успешно добавлен")
            else:
                print("Ошибка при добавлении документа в БД")  # Отладочный вывод
                self.show_error("Ошибка при добавлении документа")
                
        except Exception as e:
            print(f"Ошибка при добавлении документа: {e}")  # Отладочный вывод
            self.show_error(f"Ошибка при добавлении документа: {str(e)}")

    def _validate_document_input(self) -> bool:
        """Проверка входных данных документа"""
        if not self.current_folder:
            self.show_error("Выберите папку для документа")
            return False

        if not all([self.title_field.value, self.description_field.value]):
            self.show_error("Заполните обязательные поля")
            return False
        
        if not self.selected_file_path:
            self.show_error("Выберите файл документа")
            return False
        
        return True

    def clear_form(self):
        """Очистка формы"""
        self.title_field.value = ""
        self.description_field.value = ""
        self.tags_field.value = ""
        self.status_dropdown.value = "Активный"
        self.selected_file_path = None
        self.selected_file_name.value = "Файл не выбран"
        self.title_field.update()
        self.description_field.update()
        self.tags_field.update()
        self.status_dropdown.update()
        self.selected_file_name.update()

    def update_documents_list(self):
        """Обновление списка документов"""
        try:
            self.document_list.controls.clear()
            
            if self.current_folder is None:
                print("Текущая папка не выбрана")
                return
            
            print(f"Получение документов для папки: {self.current_folder}")
            documents = self.db.get_documents(self.current_folder)
            print(f"Получено документов: {len(documents)}")
            
            for doc in documents:
                print(f"Создание элемента для документа: {doc['title']}")
                print(f"Данные документа: {doc}")  # Добавляем вывод всех данных документа
                item = self.create_document_card(doc)  # Убедимся, что используется create_document_card
                self.document_list.controls.append(item)
            
            self.document_list.update()
            print("Список документов обновлен")
        except Exception as e:
            print(f"Ошибка при обновлении списка документов: {e}")
            self.show_error(f"Ошибка при обновлении списка документов: {str(e)}")

    def delete_document(self, doc):
        """Удаление документа"""
        def confirm_delete(e):
            if self.db.delete_document(doc["id"]):
                dialog.open = False
                self.page.update()
                self.update_documents_list()
                self.show_snack_bar("Документ успешно удален")
            else:
                self.show_error("Ошибка при удалении документа")
        
        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("Подтверждение"),
            content=ft.Text("Вы уверены, что хотите удалить этот документ?"),
            actions=[
                ft.TextButton("Отмена", on_click=lambda e: setattr(dialog, 'open', False)),
                ft.TextButton("Удалить", on_click=confirm_delete)
            ]
        )
        
        self.page.overlay.append(dialog)
        dialog.open = True
        self.page.update()

    def show_snack_bar(self, message: str):
        """Показ уведомления"""
        snack = ft.SnackBar(content=ft.Text(message))
        self.page.overlay.append(snack)
        snack.open = True
        self.page.update()

    def select_folder(self, folder_path: str):
        """Выбор папки"""
        # Обновляем текущую папку
        self.current_folder = folder_path
        # Обновляем дерево папок для отображения выделения
        self.update_folder_tree()
        # Обновляем список документов
        self.update_documents_list()
        self.page.update()

    def add_export_button(self):
        def export_to_file(e):
            current_docs = self.documents.get(self.current_folder, [])
            if not current_docs:
                self.show_error("Нет документов для экспорта")
                return
            
            export_text = "Список документов:\n\n"
            for doc in current_docs:
                export_text += f"Название: {doc.title}\n"
                export_text += f"Описание: {doc.description}\n"
                export_text += f"Статус: {doc.status}\n"
                export_text += f"Дата: {doc.date_added}\n"
                export_text += f"Теги: {', '.join(doc.tags) if doc.tags else 'Нет'}\n"
                export_text += "-" * 50 + "\n"
            
            with open("documents_export.txt", "w", encoding="utf-8") as f:
                f.write(export_text)
            
            self.show_snack_bar("Документы экспортированы в файл documents_export.txt")
        
        return ft.ElevatedButton(
            "Экспорт документов",
            icon=ft.icons.DOWNLOAD,
            on_click=export_to_file
        )

    def add_sort_dropdown(self):
        def on_sort_change(e):
            sort_type = e.control.value
            current_docs = self.documents.get(self.current_folder, [])
            
            if sort_type == "По названию":
                current_docs.sort(key=lambda x: x.title)
            elif sort_type == "По дате":
                current_docs.sort(key=lambda x: x.date_added, reverse=True)
            elif sort_type == "По статусу":
                current_docs.sort(key=lambda x: x.status)
            
            self.update_documents_list()
        
        return ft.Dropdown(
            label="Сортировка",
            width=200,
            options=[
                ft.dropdown.Option("По названию"),
                ft.dropdown.Option("По дате"),
                ft.dropdown.Option("По статусу")
            ],
            on_change=on_sort_change
        )

    def add_status_filter(self):
        def on_filter_change(e):
            status = e.control.value
            if status == "Все":
                self.update_documents_list()
                return
            
            self.document_list.controls.clear()
            current_docs = self.documents.get(self.current_folder, [])
            
            for doc in current_docs:
                if doc.status == status:
                    self.document_list.controls.append(
                        self.create_document_card(doc)
                    )
            self.document_list.update()
        
        return ft.Dropdown(
            label="Фильтр по статусу",
            width=200,
            options=[ft.dropdown.Option("Все")] + 
                    [ft.dropdown.Option(status) for status in self.statuses],
            value="Все",
            on_change=on_filter_change
        )

    def on_file_picked(self, e: ft.FilePickerResultEvent):
        """Обработка выбора файла с предпросмотром"""
        if e.files and len(e.files) > 0:
            file = e.files[0]
            if file.path.lower().endswith('.pdf'):
                self.selected_file_path = file.path
                self.selected_file_name.value = file.name
                self.selected_file_name.update()
                
                # Показываем предпромотр выбранного файла
                self.show_pdf_preview(file.path)
            else:
                self.show_error("Пожалуйста, выберите PDF файл")
                self.selected_file_path = None
                self.selected_file_name.value = "Файл не выбран"
                self.selected_file_name.update()

    def add_root_folder_dialog(self):
        """Диалог добавления корневой папки"""
        if not self.current_user.can_create_root_folder:
            self.show_error("У вас нет прав для создания корневых папок")
            return
            
        def close_dialog(e):
            dialog.open = False
            self.page.update()

        def add_folder(e):
            name = name_field.value.strip()
            if not name:
                self.show_error("Введите название папки")
                return
                
            path = f"/{name}"
            if self.db.add_folder(name, path):
                dialog.open = False
                self.page.update()
                self.refresh_ui()
                self.show_snack_bar("Папка успешно создана")
            else:
                self.show_error("Ошибка при создании папки")

        name_field = ft.TextField(
            label="Название папки",
            width=300,
            autofocus=True
        )

        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("Создать корневую папку"),
            content=ft.Column([name_field], spacing=10),
            actions=[
                ft.TextButton("Отмена", on_click=close_dialog),
                ft.TextButton("Создать", on_click=add_folder),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )

        self.page.overlay.append(dialog)
        dialog.open = True
        self.page.update()

    def add_folder_dialog(self, parent_path=None):
        """Диалог создания новой подпапи"""
        if parent_path is None:
            parent_path = self.current_folder

        def close_dialog(e):
            dialog.open = False
            self.page.update()

        def create_folder(e):
            folder_name = folder_name_field.value.strip()
            if not folder_name:
                self.show_error("Введите имя папки")
                return
            
            # Создаем путь для новой папки
            new_path = f"{parent_path}/{folder_name}".replace("//", "/")
            
            if self.db.add_folder(folder_name, new_path, parent_path):
                dialog.open = False
                self.page.update()
                self.update_folder_tree()
                self.show_snack_bar(f"Папка '{folder_name}' создана")
            else:
                self.show_error("Папка с таким именем уже существует")

        folder_name_field = ft.TextField(
            label="Имя папки",
            width=300,
            autofocus=True
        )
        
        parent_name = self.db.get_folder_name(parent_path)
        
        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text(f"Создать новую папку в '{parent_name}'"),
            content=ft.Column([folder_name_field]),
            actions=[
                ft.TextButton("Отмена", on_click=close_dialog),
                ft.TextButton("Создать", on_click=create_folder)
            ],
            actions_alignment=ft.MainAxisAlignment.END
        )
        
        self.page.overlay.append(dialog)
        dialog.open = True
        self.page.update()

    def update_folder_tree(self):
        """Обновление дерева папок"""
        print("Начало обновления дерева папок")
        
        # Показываем индикатор загрузки
        progress = ft.ProgressBar(width=300)
        self.folder_list.controls = [
            ft.Column([
                ft.Text("Загрузка папок..."),
                progress
            ], alignment=ft.MainAxisAlignment.CENTER)
        ]
        self.folder_list.update()
        
        # Перезагружаем папки из базы данных
        self.folders = self.db.get_folders()
        print(f"Папки при обновлении дерева: {self.folders}")  # Отладка
        
        if hasattr(self, 'folder_list') and self.folder_tree:
            tree_controls = self.folder_tree.build_tree()
            print(f"Построено элементов дерева: {len(tree_controls)}")  # Отладка
            self.folder_list.controls = tree_controls
            self.folder_list.update()

    def main(self, page: ft.Page):
        self.page = page
        page.title = "AVS-Архив"
        self.show_login_dialog()

    def rename_folder_dialog(self, folder_path: str):
        """Диалог переименования папки"""
        def close_dialog(e):
            dialog.open = False
            self.page.update()

        def rename_folder(e):
            new_name = name_field.value.strip()
            if not new_name:
                self.show_error("Введите имя папки")
                return
            
            parent_path = "/".join(folder_path.split("/")[:-1])
            if not parent_path:
                parent_path = "/"
            new_path = f"{parent_path}/{new_name}".replace("//", "/")
            
            if self.db.rename_folder(folder_path, new_name, new_path):
                dialog.open = False
                self.page.update()
                self.update_folder_tree()
                self.show_snack_bar(f"Папка переименована в '{new_name}'")
            else:
                self.show_error("Ошибка при переименовании папки")

        name_field = ft.TextField(
            label="Новое имя папки",
            value=self.db.get_folder_name(folder_path),
            width=300,
            autofocus=True
        )
        
        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("Переименовать папку"),
            content=ft.Column([name_field]),
            actions=[
                ft.TextButton("Отмена", on_click=close_dialog),
                ft.TextButton("Переименовать", on_click=rename_folder)
            ],
            actions_alignment=ft.MainAxisAlignment.END
        )
        
        self.page.overlay.append(dialog)
        dialog.open = True
        self.page.update()

    def delete_folder_dialog(self, folder_path: str):
        """Диалог удаления папки"""
        def close_dialog(e):
            dialog.open = False
            self.page.update()

        def delete_folder(e):
            if self.db.delete_folder(folder_path):
                dialog.open = False
                self.page.update()
                self.update_folder_tree()
                self.show_snack_bar("Папка удалена")
            else:
                self.show_error("Нельзя удалить папку с документами или подпапками")

        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("Удалить папку?"),
            content=ft.Column([
                ft.Text("Вы уверены, что хотите удалить эту папку?"),
                ft.Text("Имя папки: " + self.db.get_folder_name(folder_path), 
                       color=ft.colors.RED_400),
            ]),
            actions=[
                ft.TextButton("Отмена", on_click=close_dialog),
                ft.TextButton("Удалить", 
                            on_click=delete_folder,
                            style=ft.ButtonStyle(
                                color=ft.colors.RED_400
                            ))
            ],
            actions_alignment=ft.MainAxisAlignment.END
        )
        
        self.page.overlay.append(dialog)
        dialog.open = True
        self.page.update()

    def show_folder_menu(self, e, folder_path: str):
        """Показать меню папки с учетом прав пользователя"""
        def close_menu(e):
            menu.open = False
            self.page.update()

        def rename_action(e):
            menu.open = False
            self.page.update()
            self.rename_folder_dialog(folder_path)

        def delete_action(e):
            menu.open = False
            self.page.update()
            self.delete_folder_dialog(folder_path)

        def add_subfolder_action(e):
            menu.open = False
            self.page.update()
            self.add_folder_dialog(parent_path=folder_path)

        # Определяем, является ли папка корневой
        is_root = folder_path == "/"

        menu_items = []

        # Просмотр содержимого доступен всем
        menu_items.append(
            ft.TextButton(
                "Просмотреть содержимое",
                icon=ft.icons.FOLDER_OPEN,
                on_click=lambda e: self.select_folder(folder_path)
            )
        )
        
        # Операции с папками только для редакторов и админов
        if self.current_user.can_edit:
            menu_items.extend([
                ft.TextButton(
                    "Добавить подпапку",
                    icon=ft.icons.CREATE_NEW_FOLDER,
                    on_click=lambda e: self.add_folder_dialog(parent_path=folder_path)
                ),
                ft.TextButton(
                    "Переименовать",
                    icon=ft.icons.EDIT,
                    on_click=lambda e: self.rename_folder_dialog(folder_path)
                )
            ])
        
        if self.current_user.can_delete:
            is_root_folder = not self.folders[folder_path].get("parent_path")
            can_delete = self.current_user.can_create_root_folder if is_root_folder else True
            
            if can_delete:
                menu_items.append(
                    ft.TextButton(
                        "Удалить",
                        icon=ft.icons.DELETE,
                        on_click=lambda e: self.delete_folder_dialog(folder_path),
                        disabled=self.db.has_subfolders(folder_path) or self.db.has_documents(folder_path)
                    )
                )
        
        menu = ft.AlertDialog(
            modal=True,
            title=ft.Text(f"Действия с папкой '{self.db.get_folder_name(folder_path)}'"),
            content=ft.Column(menu_items, spacing=10),
            actions=[
                ft.TextButton("Закрыть", on_click=close_menu)
            ]
        )
        
        self.page.overlay.append(menu)
        menu.open = True
        self.page.update()

    def update_folder_hover(self, e, path: str):
        """Обновление hover эффекта папки"""
        if e.data == "true":  # Мышь наведена
            self.hovered_folder = path
        else:  # Мышь убрана
            self.hovered_folder = None
        self.update_folder_tree()

    def add_document_dialog(self):
        """Диалог добавления нового документа"""
        def close_dialog(e):
            dialog.open = False
            self.page.update()

        def pick_files(e):
            print("Открываем выбор файла...")  # Отладочный вывод
            file_picker = ft.FilePicker(
                on_result=handle_file_pick
            )
            self.page.overlay.append(file_picker)
            self.page.update()
            file_picker.pick_files(
                allow_multiple=False,
                file_type=ft.FilePickerFileType.ANY,
                allowed_extensions=["pdf", "doc", "docx", "txt", "rtf", "jpg", "jpeg", "png"]
            )

        def handle_file_pick(e):
            print("Обработка выбранного файла...")  # Отладочный вывод
            if e.files:
                file_info = e.files[0]
                self.selected_file_path = file_info.path
                self.file_path_field.value = file_info.path
                dialog.update()
                print(f"Выбран файл: {self.selected_file_path}")

        def add_document_sync(e):
            """Синхронная обертка для асинхронного метода add_document"""
            if not self._validate_document_input():
                return

            try:
                # Создаем директорию для файлов, если её нет
                files_dir = Path("document_files")
                files_dir.mkdir(exist_ok=True)

                # Получаем имя исходного файла и создаем путь для нового файла
                source_file_path = Path(self.selected_file_path)
                new_file_path = files_dir / source_file_path.name
                
                print(f"Копирование файла из {self.selected_file_path} в {new_file_path}")
                
                # Копируем файл
                import shutil
                shutil.copy2(self.selected_file_path, new_file_path)
                
                # Добавляем документ в БД
                success = self.db.add_document(
                    title=self.title_field.value,
                    description=self.description_field.value,
                    file_path=str(new_file_path),
                    folder_path=self.current_folder,
                    status=self.status_dropdown.value,
                    author=self.current_user.username,
                    cabinet=self.cabinet_field.value,
                    shelf=self.shelf_field.value,
                    box=self.box_field.value,
                    tags=[]
                )
                
                if success:
                    print("Документ успешно добавлен")
                    dialog.open = False
                    self.page.update()
                    self.update_documents_list()
                    self.show_snack_bar("Документ успешно добавлен")
                else:
                    print("Ошибка при добавлении документа в БД")
                    self.show_error("Ошибка при добавлении документа")
                    
            except Exception as e:
                print(f"Ошибка при добавлении документа: {e}")
                self.show_error(f"Ошибка при добавлении документа: {str(e)}")

        # Создаем поля формы
        self.title_field = ft.TextField(
            label="Название документа",
            width=300,
            autofocus=True
        )

        self.description_field = ft.TextField(
            label="Описание документа",
            width=300,
            multiline=True,
            min_lines=3,
            max_lines=5
        )

        # Создаем поле для пути к файлу с уменьшенной шириной
        self.file_path_field = ft.TextField(
            label="Путь к файлу",
            width=250,  # Уменьшаем ширину поля
            read_only=True,
            height=50,  # Фиксируем высоту
        )

        # Добавляем поля для расположения
        self.cabinet_field = ft.TextField(
            label="Номер шкафа",
            width=300,
        )

        self.shelf_field = ft.TextField(
            label="Номер полки",
            width=300,
        )

        self.box_field = ft.TextField(
            label="Номер короба",
            width=300,
        )

        self.status_dropdown = ft.Dropdown(
            label="Статус документа",
            width=300,
            options=[
                ft.dropdown.Option("Активный"),
                ft.dropdown.Option("На рассмотрении"),
                ft.dropdown.Option("Завершен"),
                ft.dropdown.Option("Отменен")
            ],
            value="Активный"
        )

        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("Добавить новый документ"),
            content=ft.Column([
                self.title_field,
                self.description_field,
                ft.Container(
                    content=ft.Row(
                        [
                            self.file_path_field,
                            ft.Container(
                                content=ft.IconButton(
                                    icon=ft.icons.ATTACH_FILE,
                                    icon_color=ft.colors.BLUE_400,
                                    tooltip="Прикрепить файл",
                                    on_click=pick_files,
                                ),
                                margin=ft.margin.only(right=10),
                            ),
                        ],
                        alignment=ft.MainAxisAlignment.START,
                        spacing=0,
                    ),
                    width=300,
                    padding=ft.padding.only(top=5),
                ),
                ft.Divider(),
                ft.Text("Расположение документа", size=16, weight=ft.FontWeight.BOLD),
                self.cabinet_field,
                self.shelf_field,
                self.box_field,
                ft.Divider(),
                self.status_dropdown,
            ], spacing=10),
            actions=[
                ft.TextButton("Отмена", on_click=close_dialog),
                ft.TextButton("Добавить", on_click=add_document_sync)
            ],
            actions_alignment=ft.MainAxisAlignment.END
        )

        picker = ft.FilePicker(
            on_result=handle_file_pick
        )
        self.page.overlay.append(picker)
        self.page.overlay.append(dialog)
        dialog.open = True
        self.page.update()

    def create_document_item(self, doc: Dict) -> ft.Container:
        """Создание элемента документа с учетом прав пользователя"""
        actions = []
        
        # Кнопка просмотра доступна всем
        actions.append(
            ft.IconButton(
                icon=ft.icons.VISIBILITY,
                tooltip="Просмотреть",
                on_click=lambda e, doc=doc: self.show_document_preview(doc)
            )
        )
        
        # Кнопка редактирования только для админов и редакторов
        if self.current_user.can_edit:
            actions.append(
                ft.IconButton(
                    icon=ft.icons.EDIT,
                    tooltip="Редактировать",
                    on_click=lambda e, doc=doc: self.edit_document(doc)
                )
            )
        
        # Кнопка удаления только для админов и редакторов
        if self.current_user.can_delete:
            actions.append(
                ft.IconButton(
                    icon=ft.icons.DELETE,
                    tooltip="Удалить",
                    on_click=lambda e, doc=doc: self.delete_document(doc),
                    icon_color=ft.colors.RED_400
                )
            )

        return ft.Container(
            content=ft.Row([
                ft.Icon(
                    name=ft.icons.DESCRIPTION,
                    size=40,
                    color=ft.colors.BLUE_400
                ),
                
                # Основная информация
                ft.Column([
                    ft.Text(
                        doc.get("title", "Без названия"),
                        weight=ft.FontWeight.BOLD,
                        size=16
                    ),
                    ft.Text(
                        doc.get("description", "Описание отсутствует"),
                        size=14,
                        color=ft.colors.GREY_700
                    ),
                    ft.Text(location_text, 
                           size=12, 
                           color=ft.colors.GREY_700),
                    ft.Row([
                        ft.Text(f"Статус: {doc.get('status', '')}",
                               size=12,
                               color=ft.colors.GREY_700),
                        ft.Text(f"Добавлено: {doc.get('date_added', '')}",
                               size=12,
                               color=ft.colors.GREY_700),
                    ]),
                    ft.Row([
                        ft.IconButton(
                            icon=ft.icons.PREVIEW,
                            icon_color=ft.colors.BLUE_400,
                            tooltip="Предпросмотр",
                            on_click=lambda e, doc=doc: self.show_pdf_preview(doc.get('file_path', ''))
                        ),
                        ft.IconButton(
                            icon=ft.icons.FILE_OPEN,
                            icon_color=ft.colors.GREEN_400,
                            tooltip="Открыть",
                            on_click=lambda e, doc=doc: self.open_pdf(doc.get('file_path', ''))
                        ),
                        ft.IconButton(
                            icon=ft.icons.DELETE,
                            icon_color=ft.colors.RED_400,
                            tooltip="Удалить",
                            on_click=lambda e, doc=doc: self.delete_document(doc)
                        ),
                    ])
                ], spacing=5, expand=True),
            ], alignment=ft.MainAxisAlignment.START),
            padding=10,
            border=ft.border.all(1, ft.colors.GREY_300),
            border_radius=10,
            ink=True,
            on_hover=lambda e: self.highlight_card(e)
        )

    def show_document_preview(self, doc: Dict):
        """Показать превью документа в правой панели"""
        try:
            self.current_document = doc
            
            # Создаем заголовок с информацией о документе
            header = ft.Column(
                controls=[
                    ft.Text(
                        doc.get("title", "Без названия"),
                        size=20,
                        weight=ft.FontWeight.BOLD
                    ),
                    ft.Text(
                        doc.get("description", "Описание отсутствует"),
                        size=14,
                        color=ft.colors.GREY_700
                    ),
                ],
                spacing=10
            )

            # Создаем превью файла
            preview = ft.Container(
                content=ft.Text("Выберите документ для предпросмотра"),
                alignment=ft.alignment.center,
                bgcolor=ft.colors.GREY_100,
                border_radius=10,
                padding=20,
                height=400
            )

            # Пытаемся создать превью в зависимости от типа файла
            file_path = doc.get("file_path", "")
            if file_path:
                file_ext = Path(file_path).suffix.lower()
                if file_ext in self.supported_previews:
                    preview = self.supported_previews[file_ext](file_path)

            # Создаем кнопки действий
            actions = ft.Row(
                controls=[
                    ft.ElevatedButton(
                        "Открыть",
                        icon=ft.icons.OPEN_IN_NEW,
                        on_click=lambda e: self.open_document(file_path)
                    ),
                    ft.OutlinedButton(
                        "Редактировать",
                        icon=ft.icons.EDIT,
                        on_click=lambda e: self.edit_document(doc)
                    ),
                    ft.OutlinedButton(
                        "Удалить",
                        icon=ft.icons.DELETE,
                        on_click=lambda e: self.delete_document(doc)
                    ),
                ],
                alignment=ft.MainAxisAlignment.CENTER,
                spacing=10
            )

            # Обновляем правую панель
            self.preview_panel.content.controls = [
                header,
                ft.Divider(),
                preview,
                ft.Divider(),
                actions
            ]
            self.preview_panel.update()

        except Exception as e:
            print(f"Ошибка при показе превью: {e}")
            self.show_error("Ошибка при показе превью документа")

    def cleanup_temp_files(self):
        """Очистка временных файлов"""
        import os
        for temp_file in self.temp_files:
            try:
                if os.path.exists(temp_file):
                    os.remove(temp_file)
            except Exception as e:
                print(f"Ошибка при удалении временного файла {temp_file}: {e}")
        self.temp_files.clear()

    def edit_document(self, doc: Dict):
        """Диалог редактирования документа"""
        def close_dialog(e):
            dialog.open = False
            self.page.update()

        def save_changes(e):
            try:
                # Обновляем документ в базе данных
                success = self.db.update_document(
                    doc["id"],
                    title=self.title_field.value,
                    description=self.description_field.value,
                    status=self.status_dropdown.value,
                    cabinet=self.cabinet_field.value,
                    shelf=self.shelf_field.value,
                    box=self.box_field.value
                )
                
                if success:
                    dialog.open = False
                    self.page.update()
                    self.update_documents_list()
                    self.show_document_preview(self.db.get_document(doc["id"]))
                    self.show_snack_bar("Документ успешно обновлен")
                else:
                    self.show_error("Ошибка при обновлении документа")
                    
            except Exception as e:
                print(f"Ошибка при обновлении документа: {e}")
                self.show_error("Ошибка при обновлении документа")

        # Создаем поля формы с текущими значениями
        self.title_field = ft.TextField(
            label="Название документа",
            value=doc.get("title", ""),
            width=300
        )

        self.description_field = ft.TextField(
            label="Описание документа",
            value=doc.get("description", ""),
            width=300,
            multiline=True,
            min_lines=3,
            max_lines=5
        )

        self.cabinet_field = ft.TextField(
            label="Номер шкафа",
            value=doc.get("cabinet", ""),
            width=300,
        )

        self.shelf_field = ft.TextField(
            label="Номер полки",
            value=doc.get("shelf", ""),
            width=300,
        )

        self.box_field = ft.TextField(
            label="Номер короба",
            value=doc.get("box", ""),
            width=300,
        )

        self.status_dropdown = ft.Dropdown(
            label="Статус документа",
            width=300,
            options=[
                ft.dropdown.Option("Активный"),
                ft.dropdown.Option("На рассмотрении"),
                ft.dropdown.Option("Завершен"),
                ft.dropdown.Option("Отменен")
            ],
            value=doc.get("status", "Активный")
        )

        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("Редактировать документ"),
            content=ft.Column([
                self.title_field,
                self.description_field,
                ft.Divider(),
                ft.Text("Расположение документа", size=16, weight=ft.FontWeight.BOLD),
                self.cabinet_field,
                self.shelf_field,
                self.box_field,
                ft.Divider(),
                self.status_dropdown,
            ], spacing=10),
            actions=[
                ft.TextButton("Отмена", on_click=close_dialog),
                ft.TextButton("Сохранить", on_click=save_changes)
            ],
            actions_alignment=ft.MainAxisAlignment.END
        )

        self.page.overlay.append(dialog)
        dialog.open = True
        self.page.update()

    def create_search_bar(self):
        """Создание панели поиска"""
        def on_search_change(e):
            if len(e.control.value) >= 3:  # Поиск при вводе минимум 3 символов
                self.search_documents(e.control.value)
            elif not e.control.value:  # Если поле пустое, показываем все документы
                self.update_documents_list()
        
        return ft.Row(
            controls=[
                ft.TextField(
                    hint_text="Поиск по документам...",
                    expand=True,
                    on_change=on_search_change,
                    prefix_icon=ft.icons.SEARCH,
                    suffix_icon=ft.icons.CLEAR,
                    on_submit=lambda e: self.search_documents(e.control.value),
                    border_radius=20,
                ),
            ],
            spacing=10,
        )

    def search_documents(self, query: str):
        """Выполнение поиска и обновление списка документов"""
        try:
            # Очищаем текущий список
            self.document_list.controls.clear()
            
            # Получаем результаты поиска
            results = self.db.search_documents(
                query, 
                folder_path=self.current_folder if self.current_folder else None
            )
            
            if results:
                # Добавляем найденные документы
                for doc in results:
                    self.document_list.controls.append(
                        self.create_document_item(doc)
                    )
            else:
                # Показываем сообщение, если ничего не найдено
                self.document_list.controls.append(
                    ft.Container(
                        content=ft.Column([
                            ft.Icon(ft.icons.SEARCH_OFF, size=48, color=ft.colors.GREY_400),
                            ft.Text(
                                "Документы не найдены",
                                size=16,
                                color=ft.colors.GREY_400,
                                weight=ft.FontWeight.BOLD,
                                text_align=ft.TextAlign.CENTER,
                            ),
                        ], 
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                        spacing=10),
                        padding=20,
                        alignment=ft.alignment.center,
                    )
                )
            
            self.document_list.update()
            
        except Exception as e:
            print(f"Ошибка при поиске документов: {e}")
            self.show_error("Ошибка при поиске документов")

    def show_admin_panel(self):
        """Показать панель администратора"""
        if not self.current_user.is_admin:
            self.show_error("Доступ запрещен")
            return

        def close_dialog(e):
            dialog.open = False
            self.page.update()

        def show_add_user_dialog(e):
            dialog.open = False
            self.page.update()
            self.add_user_dialog()

        def delete_user(e, username):
            if self.db.delete_user(username):
                self.show_snack_bar("Пользователь удален")
                # Получаем актуальный список пользователей
                users = self.db.get_all_users()
                users_list.controls.clear()
                for user in users:
                    if user["username"] != "admin":  # Не показываем админа в списке
                        users_list.controls.append(
                            ft.ListTile(
                                leading=ft.Icon(ft.icons.PERSON),
                                title=ft.Text(user["username"]),
                                subtitle=ft.Text(f"Роль: {user['role']}"),
                                trailing=ft.IconButton(
                                    icon=ft.icons.DELETE,
                                    icon_color=ft.colors.RED_400,
                                    on_click=lambda e, u=user: delete_user(e, u["username"])
                                ),
                            )
                        )
                dialog.update()
            else:
                self.show_error("Ошибка при удалении пользователя")

        # Создаем список пользователей
        users_list = ft.ListView(expand=1, spacing=10, padding=20)
        users = self.db.get_all_users()
        for user in users:
            if user["username"] != "admin":  # Не показываем админа в списке
                users_list.controls.append(
                    ft.ListTile(
                        leading=ft.Icon(ft.icons.PERSON),
                        title=ft.Text(user["username"]),
                        subtitle=ft.Text(f"Роль: {user['role']}"),
                        trailing=ft.IconButton(
                            icon=ft.icons.DELETE,
                            icon_color=ft.colors.RED_400,
                            on_click=lambda e, u=user: delete_user(e, u["username"])
                        ),
                    )
                )

        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("Панель администратора"),
            content=ft.Column([
                ft.Row([
                    ft.Text("Управление пользователями", size=20, weight=ft.FontWeight.BOLD),
                    ft.IconButton(
                        icon=ft.icons.ADD,
                        tooltip="Добавить пользователя",
                        on_click=show_add_user_dialog
                    )
                ]),
                ft.Divider(),
                users_list,
                ft.Divider(),
                ft.Row([
                    ft.Text("Системная информация", size=20, weight=ft.FontWeight.BOLD),
                ]),
                ft.Column([
                    ft.Text(f"Всего документов: {self.db.get_documents_count()}"),
                    ft.Text(f"Всего папок: {self.db.get_folders_count()}"),
                    ft.Text(f"Всего пользователей: {self.db.get_users_count()}"),
                ], spacing=10),
            ], scroll=ft.ScrollMode.AUTO, height=400),
            actions=[
                ft.TextButton("Закрыть", on_click=close_dialog),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )

        self.page.overlay.append(dialog)
        dialog.open = True
        self.page.update()

    def add_user_dialog(self):
        """Диалог добавления нового пользователя"""
        def close_dialog(e):
            dialog.open = False
            self.page.update()

        def add_user(e):
            username = username_field.value
            password = password_field.value
            role = role_dropdown.value

            if not all([username, password, role]):
                self.show_error("Заполните все поля")
                return

            if self.db.add_user(username, password, role):
                dialog.open = False
                self.page.update()
                self.show_snack_bar("Пользователь успешно добавлен")
            else:
                self.show_error("Ошибка при добавлении пользователя")

        username_field = ft.TextField(
            label="Имя пользователя",
            width=300
        )

        password_field = ft.TextField(
            label="Пароль",
            password=True,
            width=300
        )

        role_dropdown = ft.Dropdown(
            label="Роль пользователя",
            width=300,
            options=[
                ft.dropdown.Option("user", "Пользователь"),
                ft.dropdown.Option("editor", "Редактор"),
                ft.dropdown.Option("admin", "Администратор"),
            ],
        )

        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("Добавить пользователя"),
            content=ft.Column([
                username_field,
                password_field,
                role_dropdown,
            ], spacing=10),
            actions=[
                ft.TextButton("Отмена", on_click=close_dialog),
                ft.TextButton("Добавить", on_click=add_user),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )

        self.page.overlay.append(dialog)
        dialog.open = True
        self.page.update()

    def refresh_ui(self):
        """Обновление всего интерфейса"""
        self.update_folder_tree()
        self.update_documents_list()
        self.page.update()

if __name__ == "__main__":
    app = ArchiveApp()
    ft.app(target=app.main)