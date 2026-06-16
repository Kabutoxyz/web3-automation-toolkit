
    def _retry_request(self, method, params, max_retries=3):
        """Retry RPC request with exponential backoff."""
        for attempt in range(max_retries):
            try:
                return self._make_request(method, params)
            except RPCRateLimitError:
                wait = (2 ** attempt) + random.uniform(0, 1)
                time.sleep(wait)
            except RPCError as e:
                if attempt == max_retries - 1:
                    raise
                logger.warning(f"RPC error (attempt {attempt+1}): {e}")
        raise RPCError("Max retries exceeded")
