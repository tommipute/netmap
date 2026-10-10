import { memo } from 'react'
import { NodeResizer } from '@xyflow/react'

const HANDLE = { width: 10, height: 10 } // React Flow le tiene di questa misura a schermo a ogni zoom

/**
 * Immagine di sfondo della mappa (una per mappa), sotto tutto il resto. Si sposta e si ridimensiona solo con
 * "Sfondo della mappa" aperto (data.editing); il resto del tempo lascia passare i clic alla mappa (styles.css).
 * data: { url, opacity, editing, onResizeEnd(x, y, width) }
 */
function BackgroundNode({ data }) {
  return (
    <>
      <img className="map-background" src={data.url} alt="" draggable={false} style={{ opacity: data.opacity }} />
      {/* Dopo l'immagine, altrimenti le maniglie finiscono sotto e non si possono prendere */}
      <NodeResizer keepAspectRatio isVisible={data.editing} minWidth={80} minHeight={20}
        handleStyle={HANDLE}
        onResizeEnd={(_, p) => data.onResizeEnd(p.x, p.y, p.width)} />
    </>
  )
}

export default memo(BackgroundNode)
