import api from './api';

export const generateLinkCode = async () => {
  const response = await api.post('/whatsapp/link/generate');
  return response.data;
};

export const getLinkStatus = async () => {
  const response = await api.get('/whatsapp/link/status');
  return response.data;
};

export const unlinkWhatsApp = async () => {
  const response = await api.delete('/whatsapp/link/unlink');
  return response.data;
};

