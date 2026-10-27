export async function register() {
  if (process.env.NEXT_RUNTIME !== "nodejs") return;
  try {
    const { warmupDataBundles } = await import("./lib/server/data-source-warmup");
    await warmupDataBundles();
  } catch (err) {
    console.error("[instrumentation] warmup failed:", err);
  }
}
