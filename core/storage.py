import os
from io import BytesIO

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import FileSystemStorage

from PIL import Image, ImageOps, UnidentifiedImageError


class OptimizedMediaStorage(FileSystemStorage):
    image_extensions = {'.jpg', '.jpeg', '.png', '.webp'}

    def _save(self, name, content):
        optimized = self._optimized_content(name, content)
        return super()._save(name, optimized)

    def _optimized_content(self, name, content):
        ext = os.path.splitext(name.lower())[1]
        if ext not in self.image_extensions:
            return content

        try:
            if hasattr(content, 'seek'):
                content.seek(0)
            image = Image.open(content)
            image.load()
        except (UnidentifiedImageError, OSError, ValueError):
            if hasattr(content, 'seek'):
                content.seek(0)
            return content

        image = ImageOps.exif_transpose(image)
        max_edge = getattr(settings, 'MEDIA_IMAGE_MAX_EDGE', 2200)
        image.thumbnail((max_edge, max_edge), Image.Resampling.LANCZOS)

        output = BytesIO()
        image_format = self._format_for_extension(ext)
        save_kwargs = self._save_kwargs(image_format)

        if image_format == 'JPEG':
            if image.mode not in ('RGB', 'L'):
                background = Image.new('RGB', image.size, (255, 255, 255))
                if image.mode in ('RGBA', 'LA'):
                    background.paste(image, mask=image.getchannel('A'))
                else:
                    background.paste(image.convert('RGB'))
                image = background
            elif image.mode != 'RGB':
                image = image.convert('RGB')
        elif image_format == 'WEBP':
            if image.mode not in ('RGB', 'RGBA'):
                image = image.convert('RGBA' if 'A' in image.getbands() else 'RGB')

        image.save(output, format=image_format, **save_kwargs)
        output.seek(0)

        original_size = getattr(content, 'size', None)
        optimized_size = output.getbuffer().nbytes
        if original_size and optimized_size >= original_size:
            if hasattr(content, 'seek'):
                content.seek(0)
            return content

        return ContentFile(output.read(), name=os.path.basename(name))

    @staticmethod
    def _format_for_extension(ext):
        if ext in {'.jpg', '.jpeg'}:
            return 'JPEG'
        if ext == '.webp':
            return 'WEBP'
        return 'PNG'

    @staticmethod
    def _save_kwargs(image_format):
        if image_format == 'JPEG':
            return {
                'quality': getattr(settings, 'MEDIA_IMAGE_JPEG_QUALITY', 82),
                'optimize': True,
                'progressive': True,
            }
        if image_format == 'WEBP':
            return {
                'quality': getattr(settings, 'MEDIA_IMAGE_WEBP_QUALITY', 82),
                'method': 6,
            }
        return {'optimize': True}
