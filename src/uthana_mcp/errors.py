"""Redacted upstream errors with conservative submission outcomes."""


class APIError(RuntimeError):
    def __init__(
        self,
        message,
        *,
        category="provider_error",
        outcome="unknown",
        http_status=None,
        upstream_summary=None,
    ):
        super().__init__(message)
        self.category = category
        self.outcome = outcome
        self.http_status = http_status
        self.upstream_summary = upstream_summary

    def details(self):
        return {
            "category": self.category,
            "outcome": self.outcome,
            "http_status": self.http_status,
            "message": str(self),
            "safe_to_resubmit": self.outcome == "rejected",
            **({"upstream_summary": self.upstream_summary} if self.upstream_summary else {}),
        }


REJECTIONS = {
    "LoginRequired": (
        "authentication",
        "Uthana rejected authentication. Check the API key for the configured Uthana environment.",
    ),
    "RoleRequired": ("permission", "Uthana rejected this request because the account lacks permission."),
    "UserAccessRequired": ("permission", "Uthana rejected access to the requested asset."),
    "RegionRestricted": ("region", "Uthana rejected this model for the account's region."),
    "InsufficientBalance": ("balance", "Uthana rejected this request because the account has insufficient balance."),
}


READ_FAILURES = {
    "not_found": "Motion, character, or job not found or not accessible to this account. Verify the ID.",
    "authentication": "Uthana could not authenticate this read request. Check the API key for the configured Uthana environment.",
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


def graphql_error(result, mutation_field=None, *, read_only=False, resource=None):
    errors = result.get("errors")
    recognized = (
        isinstance(errors, list)
        and bool(errors)
        and all(isinstance(error, dict) and error.get("type") in REJECTIONS for error in errors)
    )
    categories = {REJECTIONS[error["type"]][0] for error in errors} if recognized else set()
    category = next(iter(categories)) if len(categories) == 1 else "graphql_error"
    if read_only:
        rows = errors if isinstance(errors, list) else []
        data = result.get("data")
        missing = isinstance(data, dict) and resource in data and data[resource] is None

        def missing_error(error):
            if not isinstance(error, dict):
                return False
            kind = error.get("type")
            message = str(error.get("message", "")).lower().rstrip(".")
            if kind in {"NotFound", "ResourceNotFound", "InvalidJobId"}:
                return True
            if resource == "motion" and kind == "UserAccessRequired":
                return True
            # The job resolver currently dereferences None for an absent job.
            # Match its exact known signature and null job data, not arbitrary TypeErrors.
            return resource == "job" and kind == "TypeError" and message == "'nonetype' object is not subscriptable"

        if rows and missing and all(missing_error(error) for error in rows):
            return read_error("not_found")
        return read_error(category)
    data = result.get("data")
    no_success = data is None or isinstance(data, dict) and all(value is None for value in data.values())
    if mutation_field and no_success and recognized and all(error.get("path") == [mutation_field] for error in errors):
        rejection_category, message = REJECTIONS[errors[0]["type"]]
        return APIError(message, category=rejection_category, outcome="rejected")
    if mutation_field == "create_character" and category == "graphql_error":
        rows = errors if isinstance(errors, list) else []
        summary = "Character processing did not return a confirmed result."
        category = "character_processing"
        signatures = (
            (
                "no rig found in scene",
                "character_rig",
                "No skeleton was found. Check the file rig or auto-rig setting after reconciling this request.",
            ),
            (
                "essential joints missing",
                "character_rig",
                "The skeleton is missing required pelvis, shoulder, or hip joints. Check the character's joint mapping.",
            ),
            ("auto-rigging failed", "character_rig", "Auto-rigging failed. Check the character's geometry and pose."),
            (
                "maximum number of characters",
                "character_limit",
                "The account character allowance is exhausted. Check account usage.",
            ),
            (
                "provided file is too large",
                "character_file",
                "The character exceeds the service upload limit. Reduce the file size.",
            ),
        )
        for error in rows:
            message = str(error.get("message", "")).lower() if isinstance(error, dict) else ""
            for signature, safe_category, safe_summary in signatures:
                if signature in message:
                    category, summary = safe_category, safe_summary
                    break
        return APIError(
            summary + " Inspect list_characters by name and get_request_status before another upload. "
            "If no usable character is found, contact Uthana support with the request ID.",
            category=category,
            upstream_summary=summary,
        )
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
