from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass
class VideoPrompt:
    prompt: str
    style: str = "surreal"
    duration: float = 5.0  # seconds
    aspect_ratio: str = "16:9"
    negative_prompt: str = ""


@dataclass
class VideoResult:
    video_url: str
    duration: float
    provider: str
    task_id: Optional[str] = None
    status: str = "completed"


class VideoGenerator(ABC):
    """Abstract base for video generation providers."""

    @abstractmethod
    async def generate(self, prompt: VideoPrompt) -> VideoResult:
        """Generate a video from a prompt."""
        ...

    @abstractmethod
    async def check_status(self, task_id: str) -> VideoResult:
        """Check the status of an async generation task."""
        ...
