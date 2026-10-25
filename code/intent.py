"""Multilingual authorization rules; no workflow-status shortcuts."""
import re
from models import norm

DELETE = re.compile(r'delet|eras|elimin|supprim|suppression|exclus[aã]o|削除|삭제|close.{0,30}account|account.{0,60}(closed|gone)|remove.{0,45}(account|profile|personal|data|records|name|contact)|complete.{0,20}remov|confirm.{0,50}profile is gone', re.I)
NEGATION = re.compile(r"(?:do not|don't|don’t|not a request to|not asking.{0,15}to)\s+(?:delete|erase|close|remove)|leave.{0,45}(?:in place|unchanged)|keep.{0,30}account|marketing lists only|promotional emails", re.I)
NONDELETE = re.compile(r'copy of|download my account|information request|access request|misspelled|change the email|mobile number.{0,25}out of date|resetting the login|marketing|promotional', re.I)


def classify(text):
    value = norm(text)
    clauses = re.split(r'[.!?;。]|\bbut\b', value)
    authorized = [c for c in clauses if DELETE.search(c) and not NEGATION.search(c)]
    # A denial of deletion anywhere must not be overridden by generic data words.
    if authorized and not (NEGATION.search(value) and not re.search(r'please (?:delete|erase|close|remove)', ' '.join(authorized))):
        return 'DELETE', 'DETERMINISTIC', 'explicit deletion or deletion verification'
    if NEGATION.search(value) or NONDELETE.search(value):
        return 'NON_DELETE', 'NOT_APPLICABLE', 'non-deletion purpose or explicit denial'
    return 'AMBIGUOUS', 'DETERMINISTIC', 'no recognized authorization; review required'
