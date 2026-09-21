"""Schema package.

Import from the module that owns the shape -- `app.schemas.quote`,
`app.schemas.admin`, `app.schemas.rate_card` -- rather than from here. This file
used to re-export a subset of `quote`, which drifted out of date the moment the
admin and rate card schemas were added; a partial facade is worse than none.
"""
