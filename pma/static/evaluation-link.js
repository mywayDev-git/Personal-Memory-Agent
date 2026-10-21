// Wait for the existing bootstrap/session flow before exposing the optional route.
for (let attempt=0; attempt<10; attempt++) {
  try {
    const response=await fetch('/api/v1/session');
    if(response.ok){const session=await response.json();for(const id of ['evaluation-link','evaluation-dataset-link']){const link=document.getElementById(id);if(link)link.hidden=!session.evaluation_enabled;}if(session.evaluation_enabled)window.dispatchEvent(new Event('evaluation-ready'));break;}
  } catch { /* Existing app handles session errors. */ }
  await new Promise(resolve=>setTimeout(resolve,500));
}
