"""Base scraper interface — all scrapers implement this."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional
import hashlib


@dataclass
class Job:
    title: str
    company: str
    location: str
    url: str
    source: str
    description: str = ""
    salary: str = ""
    role_type: str = ""
    deadline: str = ""
    contact_name: str = ""
    id: str = field(default="", init=False)

    def __post_init__(self):
        self.id = hashlib.md5(self.url.encode()).hexdigest()[:12]

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "company": self.company,
            "location": self.location,
            "url": self.url,
            "source": self.source,
            "description": self.description,
            "salary": self.salary,
            "role_type": self.role_type,
            "deadline": self.deadline,
            "contact_name": self.contact_name,
        }


class BaseScraper(ABC):
    @abstractmethod
    async def fetch(self) -> list[Job]:
        """Return a list of Job objects from this source."""
        ...

    def source_name(self) -> str:
        return self.__class__.__name__.replace("Scraper", "").lower()
