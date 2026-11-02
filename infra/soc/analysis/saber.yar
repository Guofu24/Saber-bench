rule saber_synthetic_marker {
    meta:
        scope = "Synthetic lab marker only; not a malware classification"
    strings:
        $marker = "SABER_LAB_SAMPLE" ascii
    condition:
        $marker
}
