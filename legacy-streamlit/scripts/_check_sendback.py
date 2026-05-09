from streamlit_webrtc import webrtc as w
import inspect

src = inspect.getsource(w)

# Find _process_offer_coro
idx = src.find('async def _process_offer_coro')
if idx == -1:
    print("Not found as function")
    idx = src.find('_process_offer_coro')
    print(f"Found reference at {idx}")
else:
    # Print the full function (up to ~3000 chars)
    end = src.find('\nasync def ', idx + 1)
    if end == -1:
        end = src.find('\ndef ', idx + 100)
    if end == -1:
        end = idx + 3000
    print(src[idx:end])
