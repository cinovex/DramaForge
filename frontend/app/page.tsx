export default function Home() {
  return (
    <main style={{ minHeight: "100vh", display: "grid", placeItems: "center", background: "#f5f7fb", color: "#263247", fontFamily: "system-ui, sans-serif" }}>
      <div style={{ textAlign: "center" }}>
        <h1>Toonflow</h1>
        <p>创作工作台正在启动。</p>
        <a href="/canvasApp/index.html#/home">进入创作首页</a>
      </div>
    </main>
  );
}
