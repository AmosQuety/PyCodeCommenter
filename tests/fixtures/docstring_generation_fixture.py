"""Fixture for exercising PyCodeCommenter's docstring GENERATION path.

Not a pytest test file (deliberately not named ``test_*``) -- every
function/class below is undocumented (or partially documented, where noted)
on purpose, so that PyCodeCommenter().from_file(...).get_patched_code() has
something real to generate. Each section is a distinct code shape the
generator is expected to handle.

Usage:
    from PyCodeCommenter import PyCodeCommenter
    patched = PyCodeCommenter().from_file(
        "scratch/docstring_generation_fixture.py"
    ).get_patched_code()
"""

from typing import Dict, List, Optional, Union
from dataclasses import dataclass


# ---------------------------------------------------------------------------
# 1. Baseline: positional params with type hints, a default, and a return
#    value. Exercises Args + Returns generation end to end.
# ---------------------------------------------------------------------------
def calculate_discount(price: float, rate: float = 0.1) -> float:
    return price * (1 - rate)


# ---------------------------------------------------------------------------
# 2. No parameters, no return value. Exercises the "Args: None." fallback
#    and a None return type.
# ---------------------------------------------------------------------------
def refresh_cache() -> None:
    _CACHE.clear()


_CACHE: Dict[str, int] = {}


# ---------------------------------------------------------------------------
# 3. Raises an exception. The validator has a Raises-section check; this
#    tests whether generation ever emits one (expected: it does not --
#    _generate_function_docstring only ever writes Args/Returns).
# ---------------------------------------------------------------------------
def parse_positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 0:
        raise ValueError(f"{value} must not be negative")
    return parsed


# ---------------------------------------------------------------------------
# 4. Generator function (yield, not return). Tests whether the generator
#    produces a sensible Returns section, a Yields section, or something
#    incorrect for a function that never actually returns a value.
# ---------------------------------------------------------------------------
def iter_batches(items: List[int], batch_size: int = 10):
    for i in range(0, len(items), batch_size):
        yield items[i : i + batch_size]


# ---------------------------------------------------------------------------
# 5. Async function. Tests async def support end to end.
# ---------------------------------------------------------------------------
async def fetch_status(endpoint: str, timeout: float = 5.0) -> bool:
    return len(endpoint) > 0 and timeout > 0


# ---------------------------------------------------------------------------
# 6. Keyword-only parameters (bare `*`). The validator is known to miss
#    these (see reports/PACKAGE_ASSESSMENT.md); this checks whether
#    generation has the same blind spot, since _generate_function_docstring
#    also only iterates func_node.args.args.
# ---------------------------------------------------------------------------
def build_report(*, title: str, sections: List[str], verbose: bool = False) -> str:
    return title + ":" + ",".join(sections)


# ---------------------------------------------------------------------------
# 7. Positional-only parameters (`/`). Same concern as #6 but for
#    args.posonlyargs instead of args.kwonlyargs.
# ---------------------------------------------------------------------------
def clamp(value: float, low: float, /, high: float = 1.0) -> float:
    return max(low, min(value, high))


# ---------------------------------------------------------------------------
# 8. *args / **kwargs. Neither lives in func_node.args.args, so this checks
#    whether the generator silently produces "Args: None." for a function
#    that clearly does take arguments.
# ---------------------------------------------------------------------------
def dispatch_event(event_name: str, *args, **kwargs) -> None:
    print(event_name, args, kwargs)


# ---------------------------------------------------------------------------
# 9. Modern type hints: PEP 604 unions, PEP 585 generics, Optional, Union.
#    Tests type inference quality/rendering in the generated Args section.
# ---------------------------------------------------------------------------
def merge_records(
    primary: dict[str, int],
    overrides: list[int] | None,
    fallback: Optional[str] = None,
    mode: Union[int, str] = "strict",
) -> dict[str, int]:
    result = dict(primary)
    return result


# ---------------------------------------------------------------------------
# 10. A class with __init__ params, extra attributes assigned in the body
#     (not just __init__ params), public/private methods, and one of each
#     special method type. Tests class docstring generation: Attributes,
#     Methods, and whether self.x = ... assignments beyond __init__'s own
#     parameters are picked up (expected: they are not --
#     _get_class_attributes only reads __init__'s parameter list).
# ---------------------------------------------------------------------------
class OrderProcessor:
    def __init__(self, customer_id: str, items: List[str]):
        self.customer_id = customer_id
        self.items = items
        self.total = 0.0  # computed attribute, not an __init__ parameter

    def add_item(self, item: str, price: float) -> None:
        self.items.append(item)
        self.total += price

    def _reset(self) -> None:
        self.items = []
        self.total = 0.0

    @property
    def item_count(self) -> int:
        return len(self.items)

    @staticmethod
    def tax_for(amount: float, rate: float = 0.07) -> float:
        return amount * rate

    @classmethod
    def empty(cls, customer_id: str) -> "OrderProcessor":
        return cls(customer_id, [])


# ---------------------------------------------------------------------------
# 11. A dataclass with class-level annotated attributes and no explicit
#     __init__. Tests whether attribute extraction (which only looks at
#     __init__'s parameter list) finds anything at all here (expected: no,
#     since there is no __init__ in source for it to inspect).
# ---------------------------------------------------------------------------
@dataclass
class Coordinates:
    latitude: float
    longitude: float
    label: str = "unnamed"

    def distance_to(self, other: "Coordinates") -> float:
        return (
            (self.latitude - other.latitude) ** 2
            + (self.longitude - other.longitude) ** 2
        ) ** 0.5


# ---------------------------------------------------------------------------
# 12. Nested function. Tests whether an inner def gets its own generated
#     docstring correctly placed inside the outer function's body.
# ---------------------------------------------------------------------------
def make_multiplier(factor: int):
    def multiply(value: int) -> int:
        return value * factor

    return multiply


# ---------------------------------------------------------------------------
# 13. Merge behavior, case A: only a one-line summary already exists.
#     Expected: summary is preserved verbatim, Args/Returns are filled in.
# ---------------------------------------------------------------------------
def normalize_whitespace(text: str) -> str:
    """Collapse runs of whitespace in the given text."""
    return " ".join(text.split())


# ---------------------------------------------------------------------------
# 14. Merge behavior, case B: a complete, already-correct Google-style
#     docstring. Expected: left untouched (or reproduced identically).
# ---------------------------------------------------------------------------
def slugify(text: str) -> str:
    """Convert text into a URL-friendly slug.

    Args:
        text (str): The text to slugify.

    Returns:
        str: The lowercased, hyphen-joined slug.
    """
    return "-".join(text.lower().split())
