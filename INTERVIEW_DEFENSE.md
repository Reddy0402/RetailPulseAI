# Interview Defense & Architectural Justifications

This document prepares the founding engineering candidate for technical defense of the **Store Intelligence Platform** architecture before leadership.

---

## 1. Why YOLO11?
* **Inference Efficiency**: YOLO11n (nano model) is the state of the art in high-speed, lightweight object detection. It runs easily at 30 FPS on standard CPUs and matches the accuracy of larger older models.
* **Precise Foot Bounding**: YOLO11 produces highly tight bounding boxes around pedestrians. Bottom-center bounding box mapping provides standard, noise-free 2D floor-coordinate points for spatial brand zone mappings.

## 2. Why ByteTrack?
* **Low-Occlusion Handling**: ByteTrack is a highly robust tracking algorithm. Standard trackers discard low-score bounding boxes during occlusions (e.g. shoppers passing behind pillars or standing close in groups). ByteTrack retains low-score detections to link trajectories, maintaining stable visitor IDs.
* **CPU Scalability**: ByteTrack uses simple Kalman filtering and Hungarian bounding-box association, requiring almost zero CPU computational cost, compared to heavy deep learning trackers.

## 3. Why PostgreSQL?
* **Transaction Safety**: Financial and operational analytics require transactional consistency. PostgreSQL connection pooling handles thousands of concurrent writes without database locks.
* **JSONB Indices**: Allows flexible schema extensions (e.g., track metadata modifications) with sub-millisecond index queries using standard GIN indices.

## 4. Why Event Sourcing?
* **Full Auditability**: Metrics (Unique Visitors, Conversions) must be derived from raw telemetry logs to prevent metric corruption. Storing only aggregates makes it impossible to re-calculate stats when algorithms improve. Storing raw event streams allows us to replay customer visits and test new rules.
* **Idempotency Safeguard**: event-sourcing with unique UUID keys guarantees that duplicate HTTP POST events are ignored.

## 5. Why Not Kafka?
* **Avoid Over-Engineering**: For 40 stores, total telemetry write rates are under ~40 events/second. Deploying, managing, and scaling an Apache Kafka cluster introduces massive infrastructure complexity, higher latency, and multiple points of failure.
* **Standard Python Stack**: Using FastAPI connection pooling directly against PostgreSQL easily handles over 10,000 requests/second, scaling comfortably to 1,000 stores.

## 6. How Would This Scale to 40 Stores?
* **Edge-Cloud Split**: Raw CCTV 1080p feeds are processed **entirely at the store edge** (on local edge nodes). This keeps video bandwidth local and avoids streaming massive video files to the cloud. Only lightweight JSON telemetry events are sent over the WAN.
* **Database Partitioning**: As the central PostgreSQL database grows (40 stores * 100k events/day = ~4M events/day), we write partition-by-range rules on the `events` table (e.g. daily or weekly partitions). This keeps indices tiny and maintains sub-millisecond query execution.

## 7. What Breaks First?
* **Camera Occlusions**: During peak weekend shopping rushes, heavy crowd density will produce tracker overlaps, causing ID swaps. 
  * *Defense*: We mitigate this by matching aspect ratios, path trajectories, and return windows in our reentry reconciler.
* **PostgreSQL Connection Latency**: If the network connection drops between the store edge and the cloud API, the worker's HTTP posts will fail.
  * *Defense*: The worker utilizes our built-in `TelemetryIngestionClient` in-memory event buffer. Telemetry is stored locally during network dropouts and flushed once the link restores, ensuring zero data loss.

## 8. Why These Anomaly Rules?
* **Real-world Retail Operations**: 
  * `QUEUE_SPIKE` directly triggers floor managers to open a new register.
  * `CONVERSION_DROP` flags product stockout or visual layout failures.
  * `DEAD_ZONE` alerts visual merchandisers to poor display layouts.
  * `STALE_FEED` alerts IT staff to camera network timeouts.

## 9. Why This Schema?
* **Separation of Raw Telemetry and Sessions**: `events` stores immutable raw track logs. `visitor_sessions` stores reconstructed shopper journeys (start time, zones traversed, checkout state). This dual structure separates writes from rapid query aggregation paths.

## 10. What AI Suggested and What Was Rejected?
* **Suggested by AI**: Running a heavy deep-learning ReID network (like OSNet or ResNet) on the edge worker to match customer embeddings.
* **Rejected by Candidate**: Rejected because deep learning embedding extraction on every frame crushed edge CPU performance below 2 FPS.
* **Founded Engineering Alternative**: We implemented a kinematic signature aspect-ratio hashing reconciler. Aspect ratios and temporal windows are compared to match reentry tracks. This runs instantly on standard CPUs, maintains low latency, and is robust.
