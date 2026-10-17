// Wait for the existing bootstrap/session flow before exposing the optional route.
for (let attempt=0; attempt<10; attempt++) {
  try {
    const response=await fetch('/api/v1/session');
    if(response.ok){const session=await response.json();document.getElementById('evaluation-link').hidden=!session.evaluation_enabled;break;}
  } catch { /* Existing app handles session errors. */ }
  await new Promise(resolve=>setTimeout(resolve,500));
}
