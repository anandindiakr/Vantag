import { useEffect, useRef, useCallback } from 'react';

interface HeatmapCanvasProps {
  gridData: number[][];
  width?: number;
  height?: number;
  className?: string;
}

/**
 * Converts a normalized heat value (0–1) to an RGBA color tuple
 * using a cold-blue → yellow → red color scale.
 */
function heatToRgba(value: number): [number, number, number, number] {
  // Clamp
  const v = Math.max(0, Math.min(1, value));

  let r = 0, g = 0, b = 0;

  if (v < 0.25) {
    // Blue → Cyan
    const t = v / 0.25;
    r = 0;
    g = Math.round(t * 255);
    b = 255;
  } else if (v < 0.5) {
    // Cyan → Green
    const t = (v - 0.25) / 0.25;
    r = 0;
    g = 255;
    b = Math.round((1 - t) * 255);
  } else if (v < 0.75) {
    // Green → Yellow
    const t = (v - 0.5) / 0.25;
    r = Math.round(t * 255);
    g = 255;
    b = 0;
  } else {
    // Yellow → Red
    const t = (v - 0.75) / 0.25;
    r = 255;
    g = Math.round((1 - t) * 255);
    b = 0;
  }

  // Alpha: low values are more transparent
  const a = Math.round(80 + v * 175);
  return [r, g, b, a];
}

export default function HeatmapCanvas({
  gridData,
  width  = 400,
  height = 300,
  className,
}: HeatmapCanvasProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  const render = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas || !gridData.length) return;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const rows = gridData.length;
    const cols = gridData[0]?.length ?? 0;
    if (rows === 0 || cols === 0) return;

    // Determine max for normalisation
    let maxVal = 0;
    for (const row of gridData) {
      for (const cell of row) {
        if (cell > maxVal) maxVal = cell;
      }
    }

    // Clear
    ctx.clearRect(0, 0, width, height);

    const cellW = width  / cols;
    const cellH = height / rows;

    const imageData = ctx.createImageData(width, height);
    const data      = imageData.data;

    for (let row = 0; row < rows; row++) {
      for (let col = 0; col < cols; col++) {
        const rawVal   = gridData[row][col] ?? 0;
        const normVal  = maxVal > 0 ? rawVal / maxVal : 0;
        const [r, g, b, a] = heatToRgba(normVal);

        // Fill each pixel inside this cell
        const x0 = Math.floor(col * cellW);
        const y0 = Math.floor(row * cellH);
        const x1 = Math.floor((col + 1) * cellW);
        const y1 = Math.floor((row + 1) * cellH);

        for (let py = y0; py < y1; py++) {
          for (let px = x0; px < x1; px++) {
            const idx  = (py * width + px) * 4;
            data[idx]     = r;
            data[idx + 1] = g;
            data[idx + 2] = b;
            data[idx + 3] = a;
          }
        }
      }
    }

    ctx.putImageData(imageData, 0, 0);

    // Smooth edges with a gentle blur via shadow (canvas compositing trick)
    ctx.filter = 'blur(4px)';
    ctx.drawImage(canvas, 0, 0);
    ctx.filter = 'none';
  }, [gridData, width, height]);

  useEffect(() => {
    render();
  }, [render]);

  return (
    <canvas
      ref={canvasRef}
      width={width}
      height={height}
      className={className}
      style={{ borderRadius: '8px', display: 'block' }}
      aria-label="Zone heatmap visualization"
    />
  );
}
