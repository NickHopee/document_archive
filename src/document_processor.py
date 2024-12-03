import asyncio
import aiofiles
from pathlib import Path
from PIL import Image
import fitz  # PyMuPDF для работы с PDF
from typing import Dict, Tuple

class DocumentProcessor:
    def __init__(self):
        self.preview_size = (200, 200)  # размер превью
        self.preview_folder = Path("previews")
        self.preview_folder.mkdir(exist_ok=True)

    async def process_document(self, file_path: str) -> Dict:
        """Асинхронная обработка загруженного документа"""
        file_path = Path(file_path)
        tasks = [
            self.generate_preview(file_path),
            self.extract_text(file_path),
            self.get_metadata(file_path)
        ]
        
        preview_path, extracted_text, metadata = await asyncio.gather(*tasks)
        
        return {
            "preview_path": str(preview_path),
            "extracted_text": extracted_text,
            "metadata": metadata
        }

    async def generate_preview(self, file_path: Path) -> Path:
        """Генерация превью документа"""
        preview_path = self.preview_folder / f"{file_path.stem}_preview.png"
        
        if preview_path.exists():
            return preview_path

        ext = file_path.suffix.lower()
        try:
            if ext in ['.jpg', '.jpeg', '.png']:
                await self._generate_image_preview(file_path, preview_path)
            elif ext == '.pdf':
                await self._generate_pdf_preview(file_path, preview_path)
            else:
                # Для неподдерживаемых форматов возвращаем путь к стандартному превью
                return Path("assets/default_preview.png")
        except Exception as e:
            print(f"Ошибка при создании превью: {e}")
            return Path("assets/error_preview.png")
            
        return preview_path

    async def _generate_image_preview(self, source: Path, target: Path):
        """Создание превью для изображений"""
        img = Image.open(source)
        img.thumbnail(self.preview_size)
        img.save(target, "PNG")

    async def _generate_pdf_preview(self, source: Path, target: Path):
        """Создание превью для PDF"""
        doc = fitz.open(source)
        if doc.page_count > 0:
            page = doc[0]
            pix = page.get_pixmap()
            pix.save(target)
        doc.close()

    async def extract_text(self, file_path: Path) -> str:
        """Извлечение текста из документа"""
        ext = file_path.suffix.lower()
        try:
            if ext == '.pdf':
                return await self._extract_pdf_text(file_path)
            elif ext in ['.txt']:
                async with aiofiles.open(file_path, 'r', encoding='utf-8') as f:
                    return await f.read()
            else:
                return ""
        except Exception as e:
            print(f"Ошибка при извлечении текста: {e}")
            return ""

    async def _extract_pdf_text(self, file_path: Path) -> str:
        """Извлечение текста из PDF"""
        doc = fitz.open(file_path)
        text = ""
        for page in doc:
            text += page.get_text()
        doc.close()
        return text

    async def get_metadata(self, file_path: Path) -> Dict:
        """Получение метаданных файла"""
        stat = file_path.stat()
        return {
            "size": stat.st_size,
            "created": stat.st_ctime,
            "modified": stat.st_mtime,
            "type": file_path.suffix.lower()
        } 