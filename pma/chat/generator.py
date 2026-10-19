"""Compatibility entry points for the existing bounded chat generation paths."""


def general(engine, data):
    from .automatic import general as generate

    return generate(engine, data)


def grounded(engine, question, session, today, **kwargs):
    return engine.generate(question, session, today, **kwargs)
