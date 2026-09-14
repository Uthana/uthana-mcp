"""Redacted upstream errors with conservative submission outcomes."""


class APIError(RuntimeError):
    def __init__(self, message, *, category="provider_error", outcome="unknown", http_status=None):
        super().__init__(message)
        self.category = category
        self.outcome = outcome
        self.http_status = http_status

    def details(self):
        return {
            "category": self.category,
            "outcome": self.outcome,
            "http_status": self.http_status,
            "message": str(self),
            "safe_to_resubmit": self.outcome == "rejected",
        }


REJECTIONS = {
    "LoginRequired": ("authentication", "Uthana rejected authentication. Correct the staging API key."),
    "RoleRequired": ("permission", "Uthana rejected this request because the account lacks permission."),
    "UserAccessRequired": ("permission", "Uthana rejected access to the requested asset."),
    "RegionRestricted": ("region", "Uthana rejected this model for the account's region."),
    "InsufficientBalance": ("balance", "Uthana rejected this request because the account has insufficient balance."),
}


READ_FAILURES = {
    "authentication": "Uthana could not authenticate this read request. Correct the staging API key.",
    "permission": "Uthana denied this read request. Check account and asset permissions.",
    "region": "Uthana denied this read request for the account's region.",
    "balance": "Uthana denied this read request because the account has insufficient balance.",
    "connection": "Could not retrieve Uthana data because the connection failed. Retry the read when available.",
    "rate_limit": "Uthana rate-limited this read request. Wait before retrying the read.",
    "http_error": "Uthana could not serve this read request. Retry the read when the service is available.",
    "graphql_error": "Uthana GraphQL request failed while reading data. No complete result was returned.",
}


def read_error(category="graphql_error", *, http_status=None):
    message = READ_FAILURES[category]
    if http_status is not None:
        message += f" HTTP {http_status}."
    return APIError(message, category=category, outcome="not_applicable", http_status=http_status)


def graphql_error(result, mutation_field=None, *, read_only=False):
    errors = result.get("errors")
    recognized = (
        isinstance(errors, list)
        and bool(errors)
        and all(isinstance(error, dict) and error.get("type") in REJECTIONS for error in errors)
    )
    categories = {REJECTIONS[error["type"]][0] for error in errors} if recognized else set()
    category = next(iter(categories)) if len(categories) == 1 else "graphql_error"
    if read_only:
        return read_error(category)
    data = result.get("data")
    no_success = data is None or isinstance(data, dict) and all(value is None for value in data.values())
    if mutation_field and no_success and recognized and all(error.get("path") == [mutation_field] for error in errors):
        rejection_category, message = REJECTIONS[errors[0]["type"]]
        return APIError(message, category=rejection_category, outcome="rejected")
    if category != "graphql_error":
        return APIError(
            f"Uthana reported {category} errors; submission may have been accepted. "
            "Inspect the saved request; do not resubmit.",
            category=category,
        )
    return APIError(
        "Uthana GraphQL request failed; submission may have been accepted. Inspect the saved request.",
        category="graphql_error",
    )
