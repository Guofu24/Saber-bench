@load policy/tuning/json-logs
redef Log::default_rotation_interval = 1hr;
# Connection/DNS/HTTP metadata only; no file extraction or packet payload archive.
# Default epoch timestamps are parsed by the shipper.
