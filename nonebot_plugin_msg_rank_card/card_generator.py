import contextlib
import random
from io import BytesIO
from pathlib import Path
from typing import Optional

import httpx
from nonebot import get_driver
from nonebot.log import logger
from PIL import Image, ImageDraw, ImageFont

from .config import Config

_resource_dir: Path = Path(__file__).parent.parent / "resources"
_resource_dir_initialized = False


def _get_config() -> Config:
    try:
        driver_config = get_driver().config
        if hasattr(driver_config, "model_dump"):
            return Config.model_validate(driver_config.model_dump())
        return Config.parse_obj(driver_config.dict())
    except Exception:
        return Config()


def _get_resource_dir() -> Path:
    global _resource_dir, _resource_dir_initialized
    if not _resource_dir_initialized:
        config = _get_config()
        if config.msg_rank_resource_path:
            _resource_dir = Path(config.msg_rank_resource_path)
        _resource_dir_initialized = True
    return _resource_dir


def _get_bg_dir() -> Path:
    return _get_resource_dir() / "bg"


def _get_frame_dir() -> Path:
    return _get_resource_dir() / "frame"


def _get_ttf_dir() -> Path:
    return _get_resource_dir() / "ttf"


# 画布尺寸
BG_WIDTH = 672
BG_HEIGHT = 1080
CARD_WIDTH = 640
CARD_HEIGHT = 80
HEAD_WIDTH = 60
HEAD_HEIGHT = 60
HEAD_X = 20
HEAD_Y = 10


class MemberInfo:
    """成员信息"""

    def __init__(self, name: str, msg_count: int, time_seconds: int, head_pic: Optional[Image.Image] = None):
        self.name = name
        self.msg_count = msg_count
        self.time_seconds = time_seconds
        self.head_pic = head_pic


class RankCardGenerator:
    """排行榜图片生成器"""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True

        self.bg_files = self._get_files(_get_bg_dir(), "bg")
        self.frame_files = self._get_files(_get_frame_dir(), "frame")
        self.font_file = self._get_first_ttf()

    def _get_files(self, dir_path: Path, name_filter: str) -> list[Path]:
        """获取目录下的文件"""
        if not dir_path.exists() or not dir_path.is_dir():
            return []
        return [f for f in dir_path.iterdir() if f.is_file() and name_filter in f.name]

    def _get_first_ttf(self) -> Optional[Path]:
        """获取第一个 ttf 字体文件"""
        ttf_dir = _get_ttf_dir()
        if not ttf_dir.exists() or not ttf_dir.is_dir():
            return None
        ttfs = [f for f in ttf_dir.iterdir() if f.is_file() and f.suffix.lower() == ".ttf"]
        return ttfs[0] if ttfs else None

    def _load_font(self, size: int) -> ImageFont.FreeTypeFont:
        """加载字体"""
        if self.font_file:
            try:
                return ImageFont.truetype(str(self.font_file), size)
            except Exception:
                pass
        # 回退到默认字体
        try:
            return ImageFont.truetype("/System/Library/Fonts/PingFang.ttc", size)
        except Exception:
            try:
                return ImageFont.truetype("/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc", size)
            except Exception:
                return ImageFont.load_default()

    def _format_time(self, seconds: int) -> str:
        """格式化时间"""
        seconds = max(0, seconds)
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        remaining = seconds % 60

        parts = []
        if hours > 0:
            parts.append(f"{hours}时")
        if minutes > 0:
            parts.append(f"{minutes}分")
        if remaining > 0 or not parts:
            parts.append(f"{remaining}秒")

        return "".join(parts)

    def _format_bg_image(self, image: Image.Image) -> Image.Image:
        """格式化背景图：缩放并裁剪到指定尺寸，添加半透明遮罩"""
        # 计算缩放比例（覆盖模式）
        scale = max(BG_WIDTH / image.width, BG_HEIGHT / image.height)
        new_width = int(image.width * scale)
        new_height = int(image.height * scale)

        # 缩放
        resized = image.resize((new_width, new_height), Image.Resampling.LANCZOS)

        # 居中裁剪
        left = (new_width - BG_WIDTH) // 2
        top = (new_height - BG_HEIGHT) // 2
        cropped = resized.crop((left, top, left + BG_WIDTH, top + BG_HEIGHT))

        # 添加白色半透明遮罩
        overlay = Image.new("RGBA", (BG_WIDTH, BG_HEIGHT), (255, 255, 255, 128))
        result = Image.alpha_composite(cropped.convert("RGBA"), overlay)

        return result

    def _create_head_mask(self) -> Image.Image:
        """创建圆形头像遮罩"""
        mask = Image.new("L", (HEAD_WIDTH, HEAD_HEIGHT), 0)
        draw = ImageDraw.Draw(mask)
        draw.ellipse((0, 0, HEAD_WIDTH, HEAD_HEIGHT), fill=255)
        return mask

    def _create_gradient_mask(self, width: int, height: int) -> Image.Image:
        """创建渐变遮罩（从左到右渐变透明）"""
        mask = Image.new("L", (width, height), 0)
        for x in range(width):
            alpha = int(255 * (1 - x / width))
            for y in range(height):
                mask.putpixel((x, y), alpha)
        return mask

    def _draw_member_card(self, member: MemberInfo, frame_path: Optional[Path], font: ImageFont.FreeTypeFont) -> Image.Image:
        """绘制单个成员卡片"""
        # 创建卡片背景
        card = Image.new("RGBA", (CARD_WIDTH, CARD_HEIGHT), (255, 255, 255, 255))
        draw = ImageDraw.Draw(card)

        # 加载边框
        frame = None
        if frame_path and frame_path.exists():
            with contextlib.suppress(Exception):
                frame = Image.open(frame_path).convert("RGBA")

        # 处理头像
        if member.head_pic:
            head = member.head_pic.copy()
            # 缩放头像
            head = head.resize((HEAD_WIDTH, HEAD_HEIGHT), Image.Resampling.LANCZOS)
            # 创建圆形遮罩
            mask = self._create_head_mask()
            # 应用圆形遮罩
            head.putalpha(mask)
            # 粘贴头像
            card.paste(head, (HEAD_X, HEAD_Y), head)

        # 绘制边框
        if frame:
            with contextlib.suppress(Exception):
                frame_resized = frame.resize((CARD_WIDTH, CARD_HEIGHT), Image.Resampling.LANCZOS)
                card = Image.alpha_composite(card, frame_resized)

        # 绘制文字
        name = member.name
        if len(name) > 12:
            name = name[:12] + "..."

        # 使用字体
        name_font = self._load_font(24)
        count_font = self._load_font(16)
        time_font = self._load_font(20)

        # 绘制名字
        draw = ImageDraw.Draw(card)
        draw.text((100, 15), name, fill=(0, 0, 0, 255), font=name_font)

        # 绘制消息数
        draw.text((100, 50), f"消息数: {member.msg_count}条", fill=(80, 80, 80, 255), font=count_font)

        # 绘制时长（右对齐）
        time_str = self._format_time(member.time_seconds)
        draw.text((440, 40), time_str, fill=(100, 100, 100, 255), font=time_font)

        return card

    def generate_card(self, members: list[MemberInfo], title: Optional[str] = None) -> Image.Image:
        """生成排行榜图片"""
        try:
            title = title or _get_config().msg_rank_title
        except Exception:
            title = title or "今日水群排行榜"

        # 创建背景
        if self.bg_files:
            try:
                bg_path = random.choice(self.bg_files)
                bg_image = Image.open(bg_path).convert("RGBA")
                background = self._format_bg_image(bg_image)
            except Exception:
                background = Image.new("RGBA", (BG_WIDTH, BG_HEIGHT), (255, 255, 255, 255))
        else:
            background = Image.new("RGBA", (BG_WIDTH, BG_HEIGHT), (255, 255, 255, 255))

        draw = ImageDraw.Draw(background)

        # 绘制标题
        title_font = self._load_font(60)
        # 计算标题居中位置
        bbox = draw.textbbox((0, 0), title, font=title_font)
        title_width = bbox[2] - bbox[0]
        title_x = (BG_WIDTH - title_width) // 2
        draw.text((title_x, 30), title, fill=(255, 0, 255, 255), font=title_font)

        # 绘制成员卡片
        for idx in range(min(len(members), 10)):
            frame_path = self.frame_files[idx] if idx < len(self.frame_files) else None
            card = self._draw_member_card(members[idx], frame_path, title_font)
            # 粘贴到背景上
            card_x = (BG_WIDTH - CARD_WIDTH) // 2
            card_y = 120 + 95 * idx
            background.paste(card, (card_x, card_y), card)

        return background

    def generate_card_bytes(self, members: list[MemberInfo], title: Optional[str] = None) -> bytes:
        """生成排行榜图片并返回 bytes"""
        image = self.generate_card(members, title)
        buffer = BytesIO()
        image.convert("RGB").save(buffer, format="PNG")
        return buffer.getvalue()


async def download_avatar(user_id: str) -> Optional[Image.Image]:
    """下载用户头像"""
    try:
        url = f"https://q1.qlogo.cn/g?b=qq&nk={user_id}&s=640"
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(url)
            if response.status_code == 200:
                return Image.open(BytesIO(response.content)).convert("RGBA")
    except Exception as e:
        logger.warning(f"下载头像失败 {user_id}: {e}")
    return None
