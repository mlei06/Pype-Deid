"""Ready-to-paste instructional blocks (optional)."""


def person_title_fewshot_rules() -> str:
    """Rules like the user example for ``Dr.`` vs ``Mr.`` PERSON spans."""
    return (
        "For the 'PERSON' entity type, there are two special cases: "
        "1. When you generate 'Dr. John', you should only extract 'John' as a PHI element; "
        "2. When you generate 'Mr. John', you should take 'Mr. John' as a PHI element."
    )
