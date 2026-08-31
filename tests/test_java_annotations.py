"""Regression guard: annotated Java classes must stay visible to the measure.

The measure is function-based, so a file the parser cannot read does not raise — it
scores as "no functions, no cost". A parser regression therefore looks exactly like
clean code, and a gate built on it silently stops blocking.

That happened: lizard 1.24.0 loses the second `@` when a bare annotation is followed
by a parenthesised one at class level (`@Entity` then `@Table(name = "owners")`), so
the class declaration is consumed as a method body and the whole file yields ZERO
functions. Every Spring/JPA entity, repository and `@RestController` written that way
became invisible, and any change to one scored impact 0 — it could never fail a gate
no matter how much complexity it accreted.

These tests assert the behaviour, not a version: whatever lizard is installed must see
methods on an annotated class, and a method added to one must cost something.
"""
from gitutil import commit, score, stage, write

ENTITY = """package fixture;

import jakarta.persistence.*;

@Entity
@Table(name = "owners")
public class Fixture {

    @Column(name = "email")
    private String email;

    public String getEmail() {
        return this.email;
    }
}
"""

# The same class with one method accreted onto it — the change a structural gate exists
# to price (it is charged for the whole surrounding class, not just its own lines).
ENTITY_PLUS_METHOD = ENTITY.replace(
    "}\n",
    """}

    @PrePersist
    void normalise() {
        if (this.email != null) {
            this.email = this.email.toLowerCase();
        }
    }
}
""", 1)

PATH = "src/main/java/fixture/Fixture.java"


def test_parser_sees_methods_on_an_annotated_class():
    from impact_gate.core.units import get_plugin
    units = get_plugin(".java").parse(ENTITY_PLUS_METHOD.encode(), PATH)
    names = {u.name for u in units}
    assert names == {"Fixture::getEmail", "Fixture::normalise"}, (
        f"the Java parser sees {names or 'NOTHING'} in an @Entity/@Table class. "
        "Every change to such a file would score 0 (lizard 1.24.0 does this).")


def test_method_added_to_an_annotated_class_costs_something(repo):
    write(repo, PATH, ENTITY)
    commit(repo, "entity")
    stage(repo, PATH, ENTITY_PLUS_METHOD)

    s = score(repo, mode="staged")
    assert s.files_changed == 1
    assert s.impact > 0, "a method accreted onto an @Entity class must not be free"
    assert s.godclass > 0 and s.mutation == 0      # the new method, not an edit
    assert any(u.name == "Fixture::normalise" for u in s.units)
