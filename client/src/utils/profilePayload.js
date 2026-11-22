export const buildProfileUpdatePayload = (user, formData) => {
  const payload = {
    full_name: formData.full_name.trim(),
    phone: formData.phone.trim(),
  };

  // The API permits self-service ward changes only for citizen accounts.
  // Staff ward assignments remain administrator-controlled.
  if ((user?.role || '').toLowerCase() === 'citizen') {
    payload.ward = formData.ward.trim();
  }

  return payload;
};
