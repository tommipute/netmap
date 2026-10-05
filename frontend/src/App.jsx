import { Link, Navigate, Route, Routes } from 'react-router-dom'
import Layout from './components/Layout'
import ChangesPage from './pages/ChangesPage'
import DevicePage from './pages/DevicePage'
import DiscoveryJobPage from './pages/DiscoveryJobPage'
import MapEditor from './pages/MapEditor'
import PrefixPage from './pages/PrefixPage'
import ResourcePage from './pages/ResourcePage'
import SearchPage from './pages/SearchPage'
import { resources } from './resources'

function NotFound() {
  return (
    <div className="page">
      <h1>Pagina non trovata</h1>
      <p>
        Torna alle <Link to="/maps">mappe</Link>.
      </p>
    </div>
  )
}

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Navigate to="/maps" replace />} />
        <Route path="maps/:id" element={<MapEditor />} />
        <Route path="devices/:id" element={<DevicePage />} />
        <Route path="prefixes/:id" element={<PrefixPage />} />
        <Route path="search" element={<SearchPage />} />
        <Route path="discovery-jobs/:id" element={<DiscoveryJobPage />} />
        <Route path="discovery/changes" element={<ChangesPage />} />
        {Object.entries(resources).map(([key, config]) => (
          // key={key}: ogni elenco riparte da zero quando si cambia sezione
          <Route key={key} path={config.path} element={<ResourcePage key={key} resourceKey={key} />} />
        ))}
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  )
}
