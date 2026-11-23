import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import { matchRoutes } from 'react-router-dom';
import { APP_ROUTE_PATHS } from '../src/appRoutePaths.js';

const appSource = readFileSync(new URL('../src/App.jsx', import.meta.url), 'utf8');
const protectedRouteSource = readFileSync(new URL('../src/components/auth/ProtectedRoute.jsx', import.meta.url), 'utf8');
const loginSource = readFileSync(new URL('../src/pages/LoginPage.jsx', import.meta.url), 'utf8');
const otpSource = readFileSync(new URL('../src/pages/OtpVerifyPage.jsx', import.meta.url), 'utf8');
const superAdminPageSource = readFileSync(new URL('../src/pages/SuperAdminDashboardPage.jsx', import.meta.url), 'utf8');
const staffProvisioningSource = readFileSync(new URL('../src/components/StaffProvisioningPanel.jsx', import.meta.url), 'utf8');
const wardSelectorSource = readFileSync(new URL('../src/components/WardSelector.jsx', import.meta.url), 'utf8');
const fieldOperationsPageSource = readFileSync(new URL('../src/pages/FieldOperationsPage.jsx', import.meta.url), 'utf8');
const fieldOperationsShellSource = readFileSync(new URL('../src/components/field-operations/FieldOperationsShell.jsx', import.meta.url), 'utf8');
const loginPortalsSource = readFileSync(new URL('../src/components/auth/ThreePortalLogins.jsx', import.meta.url), 'utf8');
const driverLoginSource = readFileSync(new URL('../src/components/auth/DriverPortalLogin.jsx', import.meta.url), 'utf8');
const collectorLoginSource = readFileSync(new URL('../src/components/auth/CollectorPortalLogin.jsx', import.meta.url), 'utf8');
const signupSource = readFileSync(new URL('../src/pages/SignupPage.jsx', import.meta.url), 'utf8');
const invitationSource = readFileSync(new URL('../src/pages/InvitationActivationPage.jsx', import.meta.url), 'utf8');
const appRoutePatterns = Object.entries(APP_ROUTE_PATHS).map(([id, path]) => ({ id, path }));

function matchedRoute(pathname) {
  const matches = matchRoutes(appRoutePatterns, { pathname });
  return matches?.at(-1)?.route.id ?? null;
}

test('retired demo URL resolves through the NotFound route', () => {
  assert.equal(matchedRoute('/demo'), 'notFound');
  assert.doesNotMatch(appSource, /DemoPage|\/demo/);
  assert.match(
    appSource,
    /<Route\s+path={APP_ROUTE_PATHS\.notFound}\s+element={<NotFoundPage\s*\/>}\s*\/>/s,
  );
});

test('unknown URLs still resolve through the NotFound route', () => {
  assert.equal(matchedRoute('/this-route-does-not-exist'), 'notFound');
});

test('public, authentication, and portal routes remain registered in App', () => {
  const expectedRoutes = [
    ['home', '/'],
    ['login', '/login'],
    ['signup', '/signup'],
    ['forgotPassword', '/forgot-password'],
    ['activate', '/activate'],
    ['otp', '/otp'],
    ['report', '/report'],
    ['track', '/track'],
    ['map', '/map'],
    ['contact', '/contact'],
    ['citizen', '/citizen'],
    ['admin', '/admin'],
    ['superAdmin', '/super-admin'],
    ['fieldOperations', '/field-operations'],
    ['collector', '/collector'],
    ['driver', '/driver'],
  ];

  for (const [routeId, pathname] of expectedRoutes) {
    assert.equal(matchedRoute(pathname), routeId, `${pathname} should match ${routeId}`);
    assert.ok(
      appSource.includes(`path={APP_ROUTE_PATHS.${routeId}}`),
      `App.jsx should use the shared ${routeId} route path`,
    );
  }
});

test('Super Admin governance route requires the Super Admin account flag', () => {
  assert.match(
    appSource,
    /path={APP_ROUTE_PATHS\.superAdmin}\s+element={\s*<ProtectedRoute allowedRoles=\{\['admin'\]\} requireSuperAdmin>/s,
  );
  assert.match(protectedRouteSource, /requireSuperAdmin && !\(authState\.user\.role\?\.toLowerCase\(\) === 'admin' && authState\.user\.is_super_admin\)/);
  assert.match(protectedRouteSource, /!requireSuperAdmin && authState\.user\.role\?\.toLowerCase\(\) === 'admin' && authState\.user\.is_super_admin/);
  assert.match(loginSource, /user\?\.is_super_admin \? '\/super-admin' : '\/admin'/);
  assert.match(otpSource, /res\.data\.user\?\.is_super_admin \? '\/super-admin' : '\/admin'/);
  assert.match(superAdminPageSource, /fetchAdministrators\(\), fetchAdminDrivers\(\), fetchAdminMetrics\(\), fetchSecurityAudit\(250\)/);
  assert.match(superAdminPageSource, /window\.confirm/);
});

test('Super Admin Command Center exposes all operational sections and uses authorized APIs', () => {
  for (const section of [
    'Overview', 'Municipal Admin Management', 'Field Staff Management', 'Citizen Management',
    'Ward Management', 'Complaint Monitoring', 'Task Monitoring', 'Analytics & Reports',
    'Audit Logs', 'Security & Account Settings',
  ]) assert.ok(superAdminPageSource.includes(section), `${section} section should exist`);
  assert.match(superAdminPageSource, /fetchGovernanceCitizens\(\)/);
  assert.match(superAdminPageSource, /fetchGovernanceCitizenComplaints\(citizen\.id\)/);
  assert.match(superAdminPageSource, /fetchGovernanceTasks\(\)/);
  assert.match(superAdminPageSource, /fetchAdminComplaints\(\)/);
  assert.match(superAdminPageSource, /fetchAdminAnalytics\(\)/);
  assert.match(superAdminPageSource, /downloadAdminExportCSV\(\)/);
  assert.match(superAdminPageSource, /updateAccountStatus\(account\.id, status, reason\?\.trim\(\)\)/);
  assert.match(superAdminPageSource, /issueStaffTemporaryPassword\(account\.id\)/);
  assert.match(superAdminPageSource, /Filter citizens by status/);
  assert.match(superAdminPageSource, /permanently retire/);
  assert.match(superAdminPageSource, /fetchWardMunicipalities\(\), fetchWards\(\)/);
  assert.match(superAdminPageSource, /createWard\(/);
  assert.match(superAdminPageSource, /updateWard\(/);
  assert.doesNotMatch(superAdminPageSource, /Wards are observed text assignments/);
  assert.match(staffProvisioningSource, /ward_id: Number\(form\.ward_id\)/);
  assert.match(wardSelectorSource, /Search ward number or name/);
});

test('Driver and Collector use a shared protected field operations route', () => {
  assert.match(
    appSource,
    /path={APP_ROUTE_PATHS\.fieldOperations}\s+element={\s*<ProtectedRoute allowedRoles=\{\['driver', 'collector'\]\}>\s*<FieldOperationsPage\s*\/>/s,
  );
  assert.match(
    appSource,
    /path={APP_ROUTE_PATHS\.driver}\s+element={\s*<ProtectedRoute allowedRoles=\{\['driver'\]\}>\s*<Navigate to={APP_ROUTE_PATHS\.fieldOperations} replace/s,
  );
  assert.match(
    appSource,
    /path={APP_ROUTE_PATHS\.collector}\s+element={\s*<ProtectedRoute allowedRoles=\{\['collector'\]\}>\s*<Navigate to={APP_ROUTE_PATHS\.fieldOperations} replace/s,
  );
  assert.match(protectedRouteSource, /if \(userRole === 'driver' \|\| userRole === 'collector'\) return <Navigate to="\/field-operations" replace \/>/);
  assert.match(loginSource, /role === 'driver' \|\| role === 'collector'[\s\S]*navigate\('\/field-operations'\)/);
  assert.match(otpSource, /role === 'driver' \|\| role === 'collector'\) navigate\('\/field-operations'\)/);
  assert.match(fieldOperationsPageSource, /api\.get\('\/auth\/me'\)/);
  assert.match(fieldOperationsPageSource, /role === 'driver' \|\| role === 'collector'/);
  assert.match(fieldOperationsPageSource, /if \(workspace === 'driver'\) return <DriverDashboardPage \/>/);
  assert.match(fieldOperationsPageSource, /if \(workspace === 'collector'\) return <CollectorDashboardPage \/>/);
  assert.match(fieldOperationsShellSource, /Field Operations Portal/);
  assert.match(fieldOperationsShellSource, /identity\?\.login_id/);
  assert.match(loginPortalsSource, /Field Operations/);
  assert.match(loginPortalsSource, /DriverPortalLogin/);
  assert.match(loginPortalsSource, /defaultRole="collector" restrictRole/);
  assert.match(signupSource, /user\?\.role === 'driver' \|\| user\?\.role === 'collector'[\s\S]*navigate\('\/field-operations'\)/);
  assert.match(invitationSource, /login\?portal=\$\{role === 'driver' \? 'driver' : 'collector'\}/);
  assert.match(loginPortalsSource, /requestedPortal = searchParams\.get\('portal'\)/);
  assert.match(driverLoginSource, /onSuccess\(result\.user\)/);
  assert.match(driverLoginSource, /phone-verification/);
  assert.match(collectorLoginSource, /mfa_code: mfaCode/);
  assert.match(collectorLoginSource, /onSuccess\(result\.user\)/);
  assert.match(collectorLoginSource, /defaultRole/);
});
