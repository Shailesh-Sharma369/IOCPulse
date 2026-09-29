import React from 'react';
import { Routes, Route } from 'react-router-dom';
import MainLayout from './components/Layout/MainLayout';
import Dashboard from './pages/Dashboard';
import Ingestion from './pages/Ingestion';
import Processing from './pages/Processing';
import RawArticles from './pages/RawArticles';
import ProcessedArticles from './pages/ProcessedArticles';
import Export from './pages/Export'; 
function App() {
  return (
    <Routes>
      <Route path="/" element={<MainLayout />}>
        <Route index element={<Dashboard />} />
        <Route path="ingestion" element={<Ingestion />} />
        <Route path="processing" element={<Processing />} />
        <Route path="raw" element={<RawArticles />} />
        <Route path="processed" element={<ProcessedArticles />} />
        <Route path="export" element={<Export />} /> {/* <--- Add Route */}
      </Route>
    </Routes>
  );
}

export default App;