"""Job handler registry: importing this module registers every background job kind.
The worker (and the API, when it runs jobs in-process) imports it at start-up."""

from app.modules.boq import jobs as boq_jobs  # noqa: F401
