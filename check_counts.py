import sys
import os
import time

sys.path.insert(0, os.path.abspath("."))
from core.sources.openalex import OpenAlexProvider

provider = OpenAlexProvider()

queries = {
    "a": '("patent classification" OR "patent retrieval" OR "patent text mining") AND ("BERT" OR "transformer" OR "pretrained language model")',
    "b": '("design science research") AND ("technology transfer" OR "intellectual property management" OR "innovation management")',
    "c": '"patent" AND "grace period" AND ("disclosure" OR "novelty")',
    "d": '("artificial intelligence" OR "large language model") AND "prior art" AND "patent"'
}

for key, q in queries.items():
    print(f"Query {key}: {q}")
    count = provider.count(q)
    print(f"  Count: {count}")
    time.sleep(1)
