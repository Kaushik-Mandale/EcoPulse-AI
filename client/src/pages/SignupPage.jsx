import React from 'react';
import { useNavigate } from 'react-router-dom';
import SplitAuthLayout from '../components/auth/SplitAuthLayout';

const SignupPage = () => {
  const navigate = useNavigate();

  const handleSuccess = (user) => {
    localStorage.setItem('ecopulse_user', JSON.stringify(user));
    if (user?.role === 'driver' || user?.role === 'collector') {
      navigate('/field-operations');
    } else if (user?.role === 'admin') {
      navigate('/admin');
    } else {
      navigate('/citizen');
    }
  };

  return <SplitAuthLayout mode="signup" onSuccessNavigation={handleSuccess} />;
};

export default SignupPage;
