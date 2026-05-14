import { Routes, Route } from "react-router-dom";
import Navbar from "./components/Navbar";
import DigestPage from "./pages/DigestPage";
import PodcastsPage from "./pages/PodcastsPage";
import MediaPage from "./pages/MediaPage";
import LivestreamsPage from "./pages/LivestreamsPage";
import PredictionsPage from "./pages/PredictionsPage";

export default function App() {
  return (
    <div className="min-h-screen">
      <Navbar />
      <main className="mx-auto max-w-3xl px-6 py-10 sm:py-14">
        <Routes>
          <Route path="/" element={<DigestPage />} />
          <Route path="/podcasts" element={<PodcastsPage />} />
          <Route path="/livestreams" element={<LivestreamsPage />} />
          <Route path="/media" element={<MediaPage />} />
          <Route path="/predictions" element={<PredictionsPage />} />
        </Routes>
      </main>
    </div>
  );
}
