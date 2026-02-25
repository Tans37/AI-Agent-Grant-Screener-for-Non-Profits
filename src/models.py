from dataclasses import dataclass
from enum import Enum
from typing import Optional, List

class Classification(Enum):
    RED = "RED"       # Reject
    YELLOW = "YELLOW" # Review
    GREEN = "GREEN"   # Priority

@dataclass
class Grant:
    id: str
    name: str # Often includes date, e.g., "Foundation Name - Date"
    foundation_name: str # Extracted or from Corporate_Kanban_Sort__c
    amount: Optional[float]
    website: Optional[str]
    focus_area: Optional[str]
    stage: str
    
    def __repr__(self):
        return f"<Grant {self.name} (${self.amount})>"

@dataclass
class ScreeningResult:
    grant: Grant
    classification: Classification
    rationale: str
    confidence_score: float # 0.0 to 1.0
    sources: Optional[List[str]] = None
