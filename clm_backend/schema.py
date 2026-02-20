from __future__ import annotations

from drf_spectacular.openapi import AutoSchema


class FeatureAutoSchema(AutoSchema):
    MODULE_TAGS: list[tuple[str, str]] = [
        ('authentication.', 'Authentication'),
        ('contracts.', 'Contracts'),
        ('contracts.template_', 'Templates'),
        ('contracts.pdf_', 'PDF'),
        ('contracts.firma_', 'Firma E-Sign'),
        ('repository.', 'Repository'),
        ('search.', 'Search'),
        ('notifications.', 'Notifications'),
        ('workflows.', 'Workflows'),
        ('approvals.', 'Approvals'),
        ('reviews.', 'Reviews'),
        ('calendar_events.', 'Calendar'),
        ('ai.', 'AI'),
    ]

    PATH_TAGS: list[tuple[str, str]] = [
        ('/api/v1/admin/', 'Admin'),
        ('/api/v1/dashboard/', 'Dashboard'),
        ('/api/auth/', 'Authentication'),
        ('/api/search/', 'Search'),
    ]

    def get_tags(self) -> list[str]:  # type: ignore[override]
        # 1) Prefer path-based tagging when obvious.
        try:
            path = (self.path or '').strip()
            for prefix, tag in self.PATH_TAGS:
                if path.startswith(prefix):
                    return [tag]
        except Exception:
            pass

        # 2) Fall back to module-based tagging.
        try:
            module = getattr(self.view, '__module__', '') or ''
            for prefix, tag in self.MODULE_TAGS:
                if module.startswith(prefix):
                    return [tag]
        except Exception:
            pass

        # 3) Default behavior.
        return super().get_tags()
