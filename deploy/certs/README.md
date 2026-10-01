# TLS sertifikaları

`docker-compose.lan.yml` bu klasördeki iki dosyayı kullanır:

- `tls.crt` — sunucu sertifikası (ara sertifikalarla birlikte)
- `tls.key` — özel anahtar

Kurumun iç sertifika otoritesinden alınmış bir sertifika kullanın; tarayıcılar ona zaten güvenir.
Yalnızca denemek için kendinden imzalı bir sertifika:

```bash
openssl req -x509 -newkey rsa:2048 -nodes -days 365 \
  -keyout tls.key -out tls.crt -subj "/CN=dialogai.sirket.local" \
  -addext "subjectAltName=DNS:dialogai.sirket.local,IP:192.168.1.50"
```

Bu dosyaları depoya eklemeyin (`.gitignore` hariç tutar).
