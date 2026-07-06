FROM python:3.11-slim

LABEL maintainer="lambda-graphs Project"
LABEL description="lambda-graphs - Tree Sitter Multi Codeview Generator"

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    graphviz \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy project files
COPY setup.py setup.cfg README.md LICENSE ./
COPY src/ ./src/

# Install the package
RUN pip install --no-cache-dir .

# Create directory for tree-sitter grammars
RUN mkdir -p /tmp/lambda-graphs && chmod 777 /tmp/lambda-graphs

# Set default command to show help
ENTRYPOINT ["lambda-graphs"]
CMD ["--help"]
