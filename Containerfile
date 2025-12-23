FROM registry.access.redhat.com/ubi9/python-312:9.6

# Switch to root to install uv
USER 0

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
RUN chmod +x /usr/local/bin/uv

# Switch back to default user
USER 1001

# Set working directory
WORKDIR /opt/app-root/src

# Copy dependency files first for better layer caching
COPY --chown=1001:0 pyproject.toml uv.lock* ./

# Sync dependencies
RUN uv sync --frozen

# Copy application code and templates
COPY --chown=1001:0 --parents config.py onboard-product.py templates/ ./

# Set the entrypoint to use uv run
ENTRYPOINT ["uv", "run", "python", "onboard-product.py"]

# Default command (can be overridden)
CMD ["--help"]
