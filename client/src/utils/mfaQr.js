import QRCode from 'qrcode';

// The otpauth URI contains the authenticator secret. Generate the QR locally;
// never send this value to a hosted QR-code service.
export const createMfaQrDataUrl = (otpauthUri) => QRCode.toDataURL(otpauthUri, {
  errorCorrectionLevel: 'M',
  margin: 2,
  width: 240,
});
