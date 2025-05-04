from langchain_community.utilities import SearxSearchWrapper
import fake_headers

headers = fake_headers.Headers(headers=True).generate()
host = "http://localhost:8080"
searx = SearxSearchWrapper(
    searx_host=host,
    headers=headers,
    unsecure=True,
    k=3
)

print(searx.run("latest news about ducks"))
