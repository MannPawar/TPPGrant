# TPP Grants System

Private Streamlit app for The Pad Project that:

- searches grant sources in real time
- ranks opportunities against TPP fit
- filters to scores greater than `6`
- generates grounded application writeups using the PDFs in:
  - `W&M MSBA x TPP/Grant Apps`
  - `W&M MSBA x TPP/Impact Reports and Decks`
  - or secure PDF uploads in the Streamlit sidebar when those folders are not bundled in the deployment

## Run locally

```powershell
& 'C:\Users\mspaw\Documents\AI TP2\venv\Scripts\pip.exe' install -r requirements.txt
& 'C:\Users\mspaw\Documents\AI TP2\venv\Scripts\streamlit.exe' run app.py
```

## Streamlit Community Cloud deployment

1. Push this repo to a **private** GitHub repository.
2. In Streamlit Community Cloud, create a new app from that private repo.
3. Set the main file path to `app.py`.
4. After deploy, use Streamlit's sharing controls to allow only approved TPP email addresses.
5. If you do not want TPP's source PDFs in the repository, upload them in the sidebar after login.

## Important notes

- GitHub Pages is not suitable for this app because the app needs a live Python backend.
- `thegrantportal.com` and `zeffy.com` may rate-limit or block some automated requests.
- The app handles blocked sources gracefully and continues with the remaining sources.
- For the most privacy-preserving setup, keep the repo private and use sidebar uploads for internal PDFs.
