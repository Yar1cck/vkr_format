from enum import Enum


class UserRole(str, Enum):
    student = "student"
    supervisor = "supervisor"
    dean = "dean"
    admin = "admin"


class DocumentStatus(str, Enum):
    pending = "pending"
    processing = "processing"
    done = "done"
    error = "error"


class ViolationStatus(str, Enum):
    auto_fixed = "auto_fixed"
    manual_required = "manual_required"
    accepted = "accepted"
    rejected = "rejected"


class ProcessingMode(str, Enum):
    full = "full"
    check_only = "check_only"


class ApprovalStatus(str, Enum):
    """Статус приёмки документа руководителем (или деканом).

    Минимальный workflow (S-18): студент отправляет на проверку, руководитель
    или декан принимает либо отклоняет с комментарием. До отправки на проверку
    значение `null` — документ существует только у студента, никому не виден
    как «ждущий проверки».
    """

    pending_review = "pending_review"
    approved = "approved"
    rejected = "rejected"
