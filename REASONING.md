# Why ImpactGate measures placement and not duplication

This page explains the background to the what and why of ImpactGate.

For the maths behind ImpactGate see [Measuring the Blast Radius of Change](https://blog.officefloor.net/2026/08/measuring-blast-radius-of-change.html).
For the full research see [the paper](https://doi.org/10.5281/zenodo.22967550).

## The short version

Two codebases that do the same thing usually contain about the same amount of logic. What makes 
one pleasant to change and the other painful is where that logic sits and how it is arranged. That 
arrangement is a design choice. ImpactGate checks the part of the choice a tool can measure 
reliably. It stays out of the part that needs a human to judge.

## The long version

### Complexity cannot be deleted, only moved

By complexity we mean how much logic the code has and how tangled it is. More branches, more
conditions, more steps, more complexity.

Here is the key fact. The essential complexity of a feature cannot be removed. If a feature
has to handle ten cases, that logic has to live somewhere. You can move it around, but you
cannot delete it. This is a well known idea called Tesler's Law, also called the Law of
Conservation of Complexity.

We measured this. We built the same feature two ways. One kept all the logic in a single
handler. The other split it across many small pieces. When you add up all the logic each
design contains, the totals come out almost the same. The amount did not change. Only the
arrangement did. The [paper](https://doi.org/10.5281/zenodo.22967550) has the full result.

### Where the logic sits is what matters

If the amount of logic is roughly fixed, then what separates good code from bad code is not
how much there is. It is where it lives.

Picture one method that is three hundred lines long and does ten different things. Now picture
ten small methods that each do one thing. They can contain the exact same logic in total. The
giant method is frightening to change, because every edit risks breaking something unrelated.
The small methods are easy, because each one is small and does one job. Same logic, very
different experience. That difference is placement, and placement is a design decision.

### Two kinds of placement decision

**1. Piling logic into one place.** When more and more logic gets added to the same class or
method, it slowly turns into a "god" class that nobody wants to touch. This one is easy for a
tool to spot, because it shows up as rising complexity in a single file.

**2. Copying logic instead of writing it once.** When you paste the same code in two places
instead of writing it once and calling it, you have added logic you did not need. This is
duplication. It also covers decisions like where to split code into helpers. A copy is extra
complexity that good design would have avoided.

### What ImpactGate checks

ImpactGate watches your change and asks a simple question. Are you piling more complexity onto
code that is already complex. Adding a tricky method to an already heavy class is expensive,
and the gate flags it. Adding the same method to a small new file is cheap, and the gate stays
quiet.

There is also an optional check for a single method that has become too deeply nested to read
easily, even when the change itself is small.

ImpactGate can do these checks on its own, in any supported language, with no outside
services, because this kind of problem leaves a clear signal in the code that a tool can read.

### What ImpactGate does not check, and why

ImpactGate does not flag duplication. This is on purpose, not a missing feature. A tool cannot
tell good duplication from bad duplication without guessing, for two reasons.

First, harmless duplication and harmful duplication look the same to a machine. Every class
has getters and setters that look nearly identical, and that is completely normal. A tool that
flagged duplicate code would complain about all of them. The duplication that actually matters
is buried in that noise, and nothing in the shape of the code tells them apart. Deciding which
is which is a judgment about meaning, not about shape.

Second, the duplication that really hurts often does not look alike at all. Imagine one part
of the code checks that a field is not empty with an if statement, and another part checks the
same thing with a validation annotation. They do the same job, but they share no matching
code. A duplicate detector sees nothing, because there is nothing matching to find.

So a duplication gate has no good setting. Turn it up and it drowns you in false alarms about
code that was fine. Turn it down and it misses the duplication that counts. Deciding whether
two pieces of code should really be one is the same kind of call as deciding how to split a
class. It needs judgment. ImpactGate will not pretend a number can make that call.

### Who should check duplication

A reviewer should, either a person or an AI model, because they can read what the code means
and decide whether two similar pieces are really one idea or two separate ones that happen to
look alike. That is not a weakness in ImpactGate. It is simply the line between what a tool can
decide and what a person has to.

Leaving duplication to review is also what keeps ImpactGate simple, fast, and the same every
time you run it. Use ImpactGate to catch complexity landing on already complex code. Use code
review for the design calls. Between them you cover a lot of ground.

### In one line

You cannot delete a feature's complexity, you can only place it, and placement is design.
ImpactGate measures the placement problem a tool can see, which is complexity piling up in one
place. It leaves the placement problem that needs judgment, which is duplication, to a
reviewer.

### The paper

The conservation result and the full argument are in the paper behind this reasoning.

Sagenschneider, D. (2026). *Conserved amount, negotiable placement: prompting moves one
architecture's complexity distribution and not the other's.* Zenodo.
[https://doi.org/10.5281/zenodo.22967550](https://doi.org/10.5281/zenodo.22967550)
