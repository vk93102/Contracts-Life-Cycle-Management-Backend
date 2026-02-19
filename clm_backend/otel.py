from __future__ import annotations

import os


def init_otel() -> None:
    enabled = (os.getenv('OTEL_ENABLED', '0') or '').strip().lower() in {'1', 'true', 'yes', 'y', 'on'}
    if not enabled:
        return

    try:
        from opentelemetry import trace
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.instrumentation.django import DjangoInstrumentor
        from opentelemetry.instrumentation.requests import RequestsInstrumentor
    except Exception:
        # Missing packages; keep app bootable.
        return

    service_name = (os.getenv('OTEL_SERVICE_NAME') or 'clm-backend').strip()

    resource = Resource.create({
        'service.name': service_name,
        'deployment.environment': (os.getenv('DEPLOYMENT_ENV') or 'dev').strip(),
    })

    provider = TracerProvider(resource=resource)
    exporter = OTLPSpanExporter()
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)

    DjangoInstrumentor().instrument()
    RequestsInstrumentor().instrument()
