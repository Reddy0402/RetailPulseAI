# Store Intelligence Platform - Technical System Design

This document details the architectural design, physical layout mapping, database relations, and analytical formulations of the **Store Intelligence Platform**.

---

## 1. System Architecture Diagram

The platform utilizes a modern edge-to-cloud split-architecture to optimize retail network bandwidth while ensuring central state consistency:

```
[ CCTV Video Feeds ] (RTSP / local MP4)
       │
       ▼ (Edge Layer - 5 FPS sub-sampled decoding)
[ YOLO11n Object Detector ] (Extracts Person BBoxes)
       │
       ▼ (ByteTrack Bounding-Box Association)
[ Bounding-Box Track Coordinates ]
       │
       ▼ (Edge Analytics Engine)
┌──────────────────────────────────────────────┐
│  • Polygon Zone Mapper (Shapely)            │
│  • Staff Exclusion Heuristic                 │
│  • DBSCAN Checkout Queue Estimator           │
│  • Signature Aspect-Ratio Reentry Reconciler │
└──────────────────────────────────────────────┘
       │
       ▼ (HTTPS POST Ingest Buffer - JSON Telemetry Batches)
[ FastAPI Ingest & Router ] (Cloud / Central Server)
       │
 ┌─────┴─────────────────────────────────────┐
 │                                           │
 ▼ (Event Sourcing Write Path)               ▼ (Observability Stream)
[ PostgreSQL Database ]                      [ WebSocket Broadcast Hub ]
 (events, visitor_sessions, logs)            (Pushes real-time dashboard events)
       │                                           │
       ▼ (State Sessionizer Engine)                ▼
[ Analytics, Funnel, Heatmap GET APIs ]  <== [ Next.js-like Dashboard UI ]
```

---

## 2. Store Brand Layout & Mapped Polygons

Based on the blueprint (`image1.png`) extracted from the store layout Excel spreadsheet, we configured screen-space zones relative to the camera frames. Physical brand bays map directly to our **Polygon Zone Mapping Engine**:

* **Entrance Zone (Left Glass Doors)**: Mapped primarily to `CAM_1`. Marks initial shopper enters and exits.
* **Top Aisle Brand Bays**: EB Korean, The Face Shop, Good Vibes, DermDoc, Minimalist, Aqualogica, Lakme Skin. Mapped to `CAM_2`.
* **Bottom Aisle Brand Bays**: Maybelline, Faces Canada, Lakme, Sugar, Swiss Beauty, Renee, Alps Goodness, Streax. Mapped to `CAM_3`.
* **Central Makeup Station**: Two-chair testing table in the center F.O.H. Mapped to `CAM_4`.
* **Cash Counter & PMU**: Billing lanes on the right side. Mapped to `CAM_5`.

---

## 3. Database Schema Design (Event Sourcing)

To achieve absolute auditability and replayability, the platform uses an **event-sourcing model**. Every customer move is captured as an immutable event. Session states are reconstructed dynamically.

### A. Raw Events (`events`)
Acts as the immutable journal. Captures telemetry:
* `event_id` (UUID): Primary key, deduplicated for idempotency.
* `visitor_id` (String): Reconciled stable customer key.
* `event_type` (String): `ZONE_ENTER`, `ZONE_EXIT`, `ZONE_DWELL`, `BILLING_QUEUE_JOIN`, `BILLING_QUEUE_ABANDON`, `REENTRY`, `PURCHASE`.
* `dwell_ms` (BigInt): Shopper stay duration in milliseconds inside that specific zone.
* `meta_data` (JSONB): Mapped track ages, occlusions, and trajectory coordinates.

### B. Visitor Sessions (`visitor_sessions`)
Reconstructed state cache for sub-millisecond metrics queries:
* `session_id` (UUID): Scoped primary session key.
* `zones_visited` (ARRAY of Strings): Records distinct brand areas visited during the shopper stay. Allows precise funnel analyses.
* `has_purchased` (Boolean): State showing if the visitor completed checkout.

---

## 4. Key Analytical Formulations

### A. North Star Conversion Rate
$$\text{Conversion Rate} = \frac{\text{Unique Customers with completed purchases}}{\text{Total Unique Customers}}$$
* Deduplicates re-entries.
* Excludes retail staff members (`is_staff = True`).
* Linked dynamically to Point-of-Sale (POS) transaction completion timestamps.

### B. Checkout Queue Depth (DBSCAN Clustering)
Active queue depth is estimated by applying Density-Based Spatial Clustering (DBSCAN) on shoppers' bottom-center coordinates within the checkout frame (`CAM_5`):
* Cluster Radius $\epsilon = 150\text{ pixels}$.
* Min Samples $N = 2$.
* Filtered on velocity ($v < 0.15\text{ m/s}$) and duration ($>15\text{s}$) to filter out bypass shoppers.

### C. Live Anomaly Alarms
A central background rules processor executes at every telemetry ingestion to flag:
1. `QUEUE_SPIKE`: Queue depth $> 5$ for more than 30 seconds.
2. `CONVERSION_DROP`: Conversion drops below the rolling 10-period average.
3. `DEAD_ZONE`: Zone visits $= 0$ in the last 15 minutes.
4. `STALE_FEED`: Ingest latency $> 60$ seconds for any active CCTV camera.
