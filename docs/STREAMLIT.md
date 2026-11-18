# Open PathSnap on another laptop

The Streamlit app runs the frozen model and decoder with the bundled demos or your own trip files. It includes the Leaflet map, observation table, optional weak-reference agreement, and CSV, GeoJSON, and JSON downloads. The browser session keeps its current result until you run another trip or close the session. Download any result you want to keep.

## Same Wi-Fi

Use Python 3.12 on the Windows laptop that will host the app. Run these commands in PowerShell from the extracted folder that contains `streamlit_ui` and `artifacts`.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r .\streamlit_ui\requirements.txt
.\.venv\Scripts\python.exe -m streamlit run .\streamlit_ui\app.py --server.address 0.0.0.0 --server.port 8501
```

Keep the app running. Open another terminal on the host and run `ipconfig`. Find the **IPv4 Address** under the active Wi-Fi adapter. On the second laptop, open `http://HOST-IP:8501`, replacing `HOST-IP` with that number. For example, use `http://192.168.1.23:8501` if the host's address is `192.168.1.23`. The second laptop only needs a browser.

## Streamlit Community Cloud

1. Push the extracted project contents to a GitHub repository. Put `streamlit_ui/`, `artifacts/`, `data/`, and `packages.txt` at the repository root.
2. Sign in to [Streamlit Community Cloud](https://share.streamlit.io/) with GitHub and choose **Create app**.
3. Select your repository and branch. Enter `streamlit_ui/app.py` as the main file path.
4. In **Advanced settings**, select **Python 3.12**, save, then deploy.
5. Open the resulting `.streamlit.app` URL on the second laptop. If the app is private, sign in with a viewer account that has access.

Community Cloud picks up the requirements in `streamlit_ui/requirements.txt` and the Linux system package in `packages.txt`. See the [official deployment guide](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/deploy).
