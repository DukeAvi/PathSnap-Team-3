const base = "/api/v1";

async function read(url, init) {
  const response = await fetch(url, init);
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(body?.error?.message || `Request failed (${response.status})`);
  }
  return response.json();
}

const jobUrl = (id) => `${base}/jobs/${encodeURIComponent(id)}`;
export const getModel = () => read(`${base}/model`);
export const getDemos = () => read(`${base}/trips/demos`);
export const getJobs = () => read(`${base}/jobs`);
export const getJob = (id) => read(jobUrl(id));
export const getMap = (id) => read(`${jobUrl(id)}/map`);
export const getDemoRoads = (trip) => read(`/assets/demo-maps/${encodeURIComponent(trip)}.geojson`);
export const getResult = (id) => read(`${jobUrl(id)}/result`);
export const exportUrl = (id, type) => `${jobUrl(id)}/exports/${type}`;
export const startDemo = (trip) => read(`${base}/trips/demos/${encodeURIComponent(trip)}`, { method: "POST" });
export function startUpload(form) {
  const data = new FormData(form);
  if (!data.get("route").name) data.delete("route");
  return read(`${base}/trips`, { method: "POST", body: data });
}
