# Load the real anyio/openai before dspy>=3.4 installs lazy proxies for them:
# - the anyio proxy breaks later anyio.abc imports;
# - with the openai proxy in sys.modules, litellm's `from openai._models import
#   BaseModel` re-enters openai's package init mid-import and dies with
#   "cannot import name 'BaseModel' from partially initialized module
#   'openai._models'" (dspy 3.4 lazy-import regression).
import anyio  # noqa: F401
import openai  # noqa: F401
