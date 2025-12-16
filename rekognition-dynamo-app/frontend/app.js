// 1) After deploying SAM, paste your API base URL here:
// Example: https://xxxxx.execute-api.us-east-1.amazonaws.com/prod
const API_BASE = "PASTE_YOUR_API_BASE_URL_HERE";
const fileInput = document.getElementById("file");
const btn = document.getElementById("btn");
const statusEl = document.getElementById("status");
const outEl = document.getElementById("out");
function setStatus(msg) {
 statusEl.textContent = msg;
}
function show(obj) {
 outEl.textContent = JSON.stringify(obj, null, 2);
}
btn.addEventListener("click", async () => {
 const file = fileInput.files?.[0];
 if (!file) {
   setStatus("Pick an image first.");
   return;
 }
 try {
   setStatus("Requesting upload URL...");
   show({});
   // 1) Get presigned URL
   const urlResp = await fetch(`${API_BASE}/upload-url`, {
     method: "POST",
     headers: { "Content-Type": "application/json" },
     body: JSON.stringify({ filename: file.name, contentType: file.type || "image/jpeg" })
   });
   const urlData = await urlResp.json();
   if (!urlResp.ok) throw new Error(urlData.error || "Failed to get upload URL");
   const { uploadUrl, key } = urlData;
   setStatus("Uploading to S3...");
   // 2) Upload directly to S3
   const putResp = await fetch(uploadUrl, {
     method: "PUT",
     headers: { "Content-Type": file.type || "image/jpeg" },
     body: file
   });
   if (!putResp.ok) throw new Error("Upload to S3 failed");
   setStatus("Running Rekognition...");
   // 3) Analyze
   const analyzeResp = await fetch(`${API_BASE}/analyze`, {
     method: "POST",
     headers: { "Content-Type": "application/json" },
     body: JSON.stringify({ key })
   });
   const analyzeData = await analyzeResp.json();
   if (!analyzeResp.ok) throw new Error(analyzeData.error || "Analyze failed");
   setStatus("Done. Results saved in DynamoDB ✅");
   show(analyzeData);
 } catch (e) {
   setStatus("Error: " + e.message);
 }
});
