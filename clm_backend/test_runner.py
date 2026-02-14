from __future__ import annotations

from django.test.runner import DiscoverRunner


class SupabaseKeepdbTestRunner(DiscoverRunner):
    """Test runner optimized for Supabase Postgres.

    Supabase often has background/pooled connections, which can make dropping the
    test database flaky ("database is being accessed by other users").

    Keeping the DB avoids noisy failures while still ensuring tests run against
    Supabase (not SQLite).
    """

    def __init__(self, *args, **kwargs):
        kwargs["keepdb"] = True
        super().__init__(*args, **kwargs)
