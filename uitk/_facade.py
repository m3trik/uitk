# !/usr/bin/python
# coding=utf-8
"""The two descriptors a facade over collaborators is built with.

uitk's large objects are facades over collaborators that own their state
(:class:`~uitk.switchboard.Switchboard`, :class:`~uitk.widgets.menu.Menu`,
:class:`~uitk.bridge.slots.BridgeSlotsBase`).
:class:`_Forward` keeps a private name that code outside the facade still
reads -- tests, subclasses, sibling widgets -- on the collaborator that owns
it; :class:`_Part` builds a collaborator on first access, for a facade whose
instances may be used before (or without) its ``__init__``.

Internal to uitk: nothing here is registered at the package root.
"""

from typing import Callable


class _Forward:
    """A class attribute that forwards to ``getattr(instance, collaborator).name``.

    Reads, writes and deletes all forward, so ``mock.patch.object(obj, name)``
    -- and a plain ``obj.<name> = value`` -- reaches the collaborator's own
    calls too. Read on the class, it returns itself, and calling that with an
    instance first calls the instance's member, so ``Class.<name>(obj, ...)``
    -- the way a class-level shim calls the original it saved -- works as it
    did for a method.

    A forward is a name, not an override point: the collaborator calls its own
    member, so a subclass method of the same name is not what it runs. A
    facade keeps every hook a subclass may override as a real method.

    Parameters:
        collaborator: The facade attribute that holds the collaborator.
        name: The collaborator's attribute the facade name stands for.
    """

    __slots__ = ("collaborator", "name")

    def __init__(self, collaborator: str, name: str):
        self.collaborator, self.name = collaborator, name

    def __get__(self, obj, owner=None):
        if obj is None:
            return self
        return getattr(getattr(obj, self.collaborator), self.name)

    def __set__(self, obj, value):
        setattr(getattr(obj, self.collaborator), self.name, value)

    def __delete__(self, obj):
        delattr(getattr(obj, self.collaborator), self.name)

    def __call__(self, obj, *args, **kwargs):
        return getattr(getattr(obj, self.collaborator), self.name)(*args, **kwargs)


class _Part:
    """A class attribute that builds a collaborator on first access.

    ``factory(instance)`` runs once per instance and its result is stored in
    the instance's ``__dict__`` under the attribute's own name, which then
    shadows this (non-data) descriptor. So a part exists whenever anything
    reaches for it: during a subclass ``__init__`` that runs before the
    facade's, and on an instance made with ``__new__`` alone (how tests stub a
    panel over just the attributes they set).

    Parameters:
        factory: Called with the facade instance; returns its collaborator.
    """

    def __init__(self, factory: Callable):
        self.factory = factory
        self.name = None

    def __set_name__(self, owner, name):
        self.name = name

    def __get__(self, obj, owner=None):
        if obj is None:
            return self
        part = self.factory(obj)
        obj.__dict__[self.name] = part
        return part
