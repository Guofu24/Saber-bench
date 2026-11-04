# DFIR · Disk, filesystem, dữ liệu bị xóa và super timeline

Chọn topic này khi có ảnh đĩa/volume, logical extraction hoặc câu hỏi file đã tồn tại, đổi hay bị xóa.
Input phải có evidence ID, hash, loại ảnh, segments, acquisition log và phạm vi được thu.

## Đi từ image tới artifact

1. Verify working copy/segments và ghi format, image size, sector size, partition table, encryption,
   filesystem/version. Phân biệt disk image, partition image và logical files; offset của volume image có thể là 0.
2. Liệt kê partitions bằng parser hỗ trợ, chọn volume theo OS/user/path của case. Ghi offset và **đơn vị**;
   không lấy byte offset làm sector offset hoặc mặc định 512 bytes khi thiết bị khác.
3. Dùng read-only parser/mount phù hợp filesystem. Không chạy repair/journal replay hay boot image gốc.
   Nếu cần phục hồi cấu trúc, làm trên derivative và giữ diff/method; không tự sửa để parser báo sạch.
4. Trích artifact có file/inode/MFT reference, stream/attribute, path và bytes/hash; ghi allocated/deleted,
   sparse/compressed/encrypted, errors và nơi output. Không mở/chạy recovered binary trên host làm việc.
5. Đối chiếu metadata, journal và log độc lập. File record bị tái sử dụng, hard link, rename và alternate streams
   có thể làm path không còn đại diện đúng nội dung. Carving có thể thiếu path, chủ sở hữu và timestamps.

## Ví dụ TSK trên bản sao, cú pháp Bash

Các tham số minh họa chỉ dùng sau khi xác minh offset/sector size/inode từ ảnh cụ thể:

```bash
mmls /cases/INC-001/working/disk.raw
fsstat -o 2048 -b 512 /cases/INC-001/working/disk.raw
fls -r -p -o 2048 -b 512 /cases/INC-001/working/disk.raw > file-list.txt
icat -o 2048 -b 512 /cases/INC-001/working/disk.raw 12345 > recovered.bin
```

`mmls` phân tích bố cục volume; `fls` liệt kê tên; `icat` trích bytes từ metadata address.
Lưu output trong case workspace và hash derivative. Các số trên là ví dụ, không phải preset cho mọi ảnh.
`fls -r` không tự đi vào mọi deleted directory; trích file thành công không bảo đảm file đầy đủ/nguyên trạng.
Kiểm `-i list`/`-f list` và help bản cài khi định dạng không hỗ trợ. Không gọi các lệnh này là acquisition máy live.

## Giới hạn filesystem

| Nguồn | Cần đối chiếu |
|---|---|
| NTFS | MFT record/sequence, SI/FN timestamps, USN/file reference, LogFile, ADS; journal wrap và timestamp manipulation |
| ext4/XFS/Btrfs | inode/metadata, journal/snapshot được hỗ trợ; ctime khác creation, mount flags ảnh hưởng atime |
| APFS | Volume/snapshot identifiers, encryption và parser/version; không suy hỗ trợ APFS từ hỗ trợ HFS+ |
| SSD/flash | TRIM/garbage collection, wear leveling và vùng controller không cung cấp; không hứa undelete |
| FDE/locked volume | Key escrow/quyền giải mã từ owner; không lấy thất bại giải mã làm bằng chứng không có dữ liệu |
| SQLite/browser | Giữ DB cùng WAL/journal/SHM khi phù hợp, snapshot consistency; phân biệt deleted row với nội dung đã đọc |

## Timeline từ artifact

Plaso trích events vào storage file; giữ phiên bản, parser/filter, preprocess clock và extraction warnings.
Ví dụ: `log2timeline.py --storage-file timeline.plaso /cases/INC-001/working/disk.E01`.
Chọn partitions/VSS có căn cứ; export bằng psort phù hợp bản cài và lưu lineage tới raw artifact.
Event count lớn không chứng minh đầy đủ; kiểm dropped/failed parsers và kiểm thủ công một mẫu quan trọng.
Một artifact nhiều timestamps không phải nhiều hành vi độc lập. Giữ ý nghĩa từng field và uncertainty.

Nguồn chính thức: [TSK mmls](https://www.sleuthkit.org/sleuthkit/man/mmls.html),
[fsstat](https://www.sleuthkit.org/sleuthkit/man/fsstat.html),
[fls](https://www.sleuthkit.org/sleuthkit/man/fls.html), [icat](https://www.sleuthkit.org/sleuthkit/man/icat.html),
[Plaso log2timeline](https://plaso.readthedocs.io/en/latest/sources/user/Using-log2timeline.html).
