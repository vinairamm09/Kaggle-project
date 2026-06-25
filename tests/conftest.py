import os
import sys
from unittest.mock import MagicMock

# Set required environment variables
os.environ["GOOGLE_CLOUD_PROJECT"] = "mock-project"
os.environ["INTEGRATION_TEST"] = "TRUE"

# Mock google.auth.default before anything else is imported
import google.auth
from google.auth import credentials

mock_cred = MagicMock(spec=credentials.Credentials)
google.auth.default = lambda *args, **kwargs: (mock_cred, "mock-project")

# Mock google.cloud.logging.Client
import google.cloud.logging
mock_logging_client = MagicMock()
mock_logger = MagicMock()
mock_logging_client.logger.return_value = mock_logger
google.cloud.logging.Client = lambda *args, **kwargs: mock_logging_client
