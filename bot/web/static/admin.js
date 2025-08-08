document.addEventListener('DOMContentLoaded', () => {
    const token = getAuthToken();
    if (!token) {
        window.location.href = '/login';
        return;
    }

    // This script is only for the admin.html page.
    // If the main user list doesn't exist, stop execution.
    const userListBody = document.getElementById('user-list-body');
    if (!userListBody) {
        return;
    }

    const headers = { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' };
    
    // --- User Management Elements ---
    const createUserForm = document.getElementById('create-user-form');
    const changePasswordForm = document.getElementById('change-password-form');
    const adminModal = document.getElementById('admin-change-password-modal');
    const adminModalForm = document.getElementById('admin-change-password-form-modal');
    const modalUsername = document.getElementById('modal-username');
    const modalUserId = document.getElementById('modal-user-id');
    const modalNewPassword = document.getElementById('modal-new-password');
    const modalCancelBtn = document.getElementById('modal-cancel-btn');
    const modalMessageEl = document.getElementById('modal-password-change-message');

    // --- Squad Template Elements ---
    const createTemplateForm = document.getElementById('create-template-form');
    const addDefinitionBtn = document.getElementById('add-definition-btn');
    const definitionsContainer = document.getElementById('template-definitions-container');
    const templateList = document.getElementById('template-list');
    const templateFormTitle = document.getElementById('template-form-title');
    const saveTemplateBtn = document.getElementById('save-template-btn');
    const cancelEditBtn = document.getElementById('cancel-edit-btn');
    const editingTemplateIdInput = document.getElementById('editing-template-id');
    let allTemplates = [];

    const RSVP_POOLS = ["Commander", "Infantry", "Armour", "Recon", "Pathfinders", "Artillery", "Unassigned"];
    const SQUAD_TYPES = ["Command", "Infantry", "Armour", "Recon", "Artillery", "Reserves"];

    function validatePassword(password) {
        const validations = {
            length: password.length >= 8,
            case: /[a-z]/.test(password) && /[A-Z]/.test(password),
            number: /[0-9]/.test(password),
            special: /[!@#$%^&*()_+\-=\[\]{}|;':",./<>?]/.test(password)
        };
        return Object.values(validations).every(Boolean);
    }

    // --- Squad Template Functions ---
    const addDefinitionRow = (definition = null) => {
        const rowId = `def-row-${Date.now()}`;
        const div = document.createElement('div');
        div.className = 'grid grid-cols-1 md:grid-cols-7 gap-2 items-center border-t border-gray-600 pt-3';
        div.id = rowId;

        div.innerHTML = `
            <input type="text" placeholder="Squad Name (e.g., Attack)" class="md:col-span-2 bg-gray-600 border-gray-500 rounded-md p-2" data-field="squad_name" value="${definition?.squad_name || ''}" required>
            <input type="number" value="${definition?.default_count || 1}" min="0" class="bg-gray-600 border-gray-500 rounded-md p-2" data-field="default_count" required>
            <select class="bg-gray-600 border-gray-500 rounded-md p-2" data-field="source_rsvp_pool">${RSVP_POOLS.map(p => `<option value="${p}" ${definition?.source_rsvp_pool === p ? 'selected' : ''}>${p}</option>`).join('')}</select>
            <select class="bg-gray-600 border-gray-500 rounded-md p-2" data-field="squad_type">${SQUAD_TYPES.map(t => `<option value="${t}" ${definition?.squad_type === t ? 'selected' : ''}>${t}</option>`).join('')}</select>
            <select class="md:col-span-1 bg-gray-600 border-gray-500 rounded-md p-2" data-field="naming_convention">
                <option value="none" ${definition?.naming_convention === 'none' ? 'selected' : ''}>None</option>
                <option value="alpha" ${definition?.naming_convention === 'alpha' ? 'selected' : ''}>Alpha (A, B)</option>
                <option value="numeric" ${definition?.naming_convention === 'numeric' ? 'selected' : ''}>Numeric (1.1, 1.2)</option>
            </select>
            <button type="button" class="text-red-500 hover:text-red-700 font-bold justify-self-center" onclick="document.getElementById('${rowId}').remove()">X</button>
        `;
        definitionsContainer.appendChild(div);
    };

    const resetTemplateForm = () => {
        templateFormTitle.textContent = 'Create New Template';
        saveTemplateBtn.textContent = 'Save Template';
        cancelEditBtn.classList.add('hidden');
        createTemplateForm.reset();
        editingTemplateIdInput.value = '';
        definitionsContainer.querySelectorAll('.grid').forEach(row => {
            if (row.querySelector('input')) row.remove();
        });
        addDefinitionRow();
    };

    const loadTemplates = async () => {
        try {
            const response = await fetch('/api/templates', { headers });
            if (!response.ok) throw new Error('Failed to load templates');
            allTemplates = await response.json();
            
            templateList.innerHTML = '';
            allTemplates.forEach(template => {
                const div = document.createElement('div');
                div.className = 'bg-gray-700 p-3 rounded-md flex justify-between items-center';
                div.innerHTML = `
                    <span class="font-semibold">${template.template_name}</span>
                    <div>
                        <button data-template-id="${template.template_id}" class="edit-template-btn text-blue-400 hover:text-blue-600 mr-4">Edit</button>
                        <button data-template-id="${template.template_id}" class="delete-template-btn text-red-500 hover:text-red-700">Delete</button>
                    </div>
                `;
                templateList.appendChild(div);
            });
        } catch (error) {
            templateList.innerHTML = `<p class="text-red-400">${error.message}</p>`;
        }
    };
    
    addDefinitionBtn.addEventListener('click', () => addDefinitionRow());
    cancelEditBtn.addEventListener('click', resetTemplateForm);

    createTemplateForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const templateName = document.getElementById('template-name').value;
        const definitions = [];
        definitionsContainer.querySelectorAll('.grid').forEach(row => {
            if (row.querySelector('input')) {
                definitions.push({
                    squad_name: row.querySelector('[data-field="squad_name"]').value,
                    default_count: parseInt(row.querySelector('[data-field="default_count"]').value, 10),
                    source_rsvp_pool: row.querySelector('[data-field="source_rsvp_pool"]').value,
                    squad_type: row.querySelector('[data-field="squad_type"]').value,
                    naming_convention: row.querySelector('[data-field="naming_convention"]').value,
                });
            }
        });

        if (!templateName || definitions.length === 0) {
            alert('Template name and at least one definition are required.');
            return;
        }

        const editingId = editingTemplateIdInput.value;
        const method = editingId ? 'PUT' : 'POST';
        const url = editingId ? `/api/templates/${editingId}` : '/api/templates';

        try {
            const response = await fetch(url, {
                method: method,
                headers: headers,
                body: JSON.stringify({ template_name: templateName, definitions: definitions })
            });
            if (!response.ok) throw new Error((await response.json()).detail || 'Failed to save template');
            
            resetTemplateForm();
            await loadTemplates();
            alert(`Template ${editingId ? 'updated' : 'saved'} successfully!`);

        } catch (error) {
            alert(`Error: ${error.message}`);
        }
    });

    templateList.addEventListener('click', async (e) => {
        const target = e.target;
        if (target.classList.contains('delete-template-btn')) {
            const templateId = target.dataset.templateId;
            if (confirm('Are you sure you want to delete this template?')) {
                try {
                    const response = await fetch(`/api/templates/${templateId}`, { method: 'DELETE', headers });
                    if (!response.ok) throw new Error('Failed to delete');
                    await loadTemplates();
                } catch {
                    alert('Error deleting template.');
                }
            }
        } else if (target.classList.contains('edit-template-btn')) {
            const templateId = target.dataset.templateId;
            const template = allTemplates.find(t => t.template_id == templateId);
            if (!template) return;

            templateFormTitle.textContent = `Editing: ${template.template_name}`;
            saveTemplateBtn.textContent = 'Update Template';
            cancelEditBtn.classList.remove('hidden');
            editingTemplateIdInput.value = template.template_id;
            document.getElementById('template-name').value = template.template_name;
            
            definitionsContainer.querySelectorAll('.grid').forEach(row => {
                if (row.querySelector('input')) row.remove();
            });

            template.definitions.forEach(def => addDefinitionRow(def));
        }
    });

    // --- User Management Functions ---
    async function loadUsers() {
        try {
            const response = await fetch('/api/users/', { headers: { 'Authorization': `Bearer ${token}` } });
            if (response.status === 401) { window.location.href = '/login'; return; }
            if (!response.ok) throw new Error((await response.json()).detail || 'Failed to fetch users');
            
            const users = await response.json();
            userListBody.innerHTML = '';
            users.forEach(user => {
                const tr = document.createElement('tr');
                tr.className = 'border-b border-gray-700';
                tr.innerHTML = `
                    <td class="px-6 py-4">${user.username}</td>
                    <td class="px-6 py-4"><span class="px-2 inline-flex text-xs leading-5 font-semibold rounded-full ${user.is_active ? 'bg-green-900 text-green-300' : 'bg-red-900 text-red-300'}">${user.is_active ? 'Active' : 'Disabled'}</span></td>
                    <td class="px-6 py-4">${user.is_admin ? 'Admin' : 'User'}</td>
                    <td class="px-6 py-4 text-sm font-medium space-x-2">
                        <button data-action="toggle-active" data-id="${user.id}" class="text-yellow-400 hover:text-yellow-600">${user.is_active ? 'Disable' : 'Enable'}</button>
                        <button data-action="toggle-admin" data-id="${user.id}" class="text-indigo-400 hover:text-indigo-600">${user.is_admin ? 'Revoke Admin' : 'Make Admin'}</button>
                        <button data-action="change-password" data-id="${user.id}" data-username="${user.username}" class="text-blue-400 hover:text-blue-600">Change Password</button>
                        <button data-action="delete" data-id="${user.id}" class="text-red-500 hover:text-red-700">Delete</button>
                    </td>
                `;
                userListBody.appendChild(tr);
            });
        } catch (error) {
            console.error('Error loading users:', error);
            alert('Could not load user data.');
        }
    }

    createUserForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const username = e.target['new-username'].value;
        const password = e.target['new-password'].value;
        const isAdmin = e.target['new-is-admin'].checked;
        if (!validatePassword(password)) {
            alert('Error: New user password does not meet all requirements.');
            return;
        }
        try {
            const response = await fetch('/api/users/', {
                method: 'POST',
                headers: headers,
                body: JSON.stringify({ username, password, is_admin: isAdmin })
            });
            if (!response.ok) { throw new Error((await response.json()).detail || 'Failed to create user'); }
            createUserForm.reset();
            loadUsers();
        } catch (error) {
            alert(`Error: ${error.message}`);
        }
    });

    if (changePasswordForm) {
        const newPasswordInput = document.getElementById('new-password-change');
        const messageEl = document.getElementById('password-change-message');
        const pwValidators = {
            length: document.getElementById('pw-length'),
            case: document.getElementById('pw-case'),
            number: document.getElementById('pw-number'),
            special: document.getElementById('pw-special'),
        };

        function updateValidationUI(password) {
            const validations = {
                length: password.length >= 8,
                case: /[a-z]/.test(password) && /[A-Z]/.test(password),
                number: /[0-9]/.test(password),
                special: /[!@#$%^&*()_+\-=\[\]{}|;':",./<>?]/.test(password)
            };
            Object.keys(validations).forEach(key => {
                pwValidators[key].style.color = validations[key] ? 'lightgreen' : 'inherit';
            });
        }

        newPasswordInput.addEventListener('input', () => updateValidationUI(newPasswordInput.value));

        changePasswordForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            const currentPassword = document.getElementById('current-password').value;
            const newPassword = newPasswordInput.value;
            const confirmPassword = document.getElementById('confirm-new-password').value;
            
            messageEl.textContent = '';
            messageEl.classList.remove('text-red-400', 'text-green-400');

            if (newPassword !== confirmPassword) {
                messageEl.textContent = 'Error: New passwords do not match.';
                messageEl.classList.add('text-red-400');
                return;
            }
            if (!validatePassword(newPassword)) {
                messageEl.textContent = 'Error: New password does not meet all requirements.';
                messageEl.classList.add('text-red-400');
                return;
            }

            try {
                const response = await fetch('/api/users/me/password', {
                    method: 'PUT',
                    headers: headers,
                    body: JSON.stringify({ current_password: currentPassword, new_password: newPassword })
                });
                if (!response.ok) { throw new Error((await response.json()).detail || 'Failed to change password'); }
                
                messageEl.textContent = 'Password changed successfully!';
                messageEl.classList.add('text-green-400');
                changePasswordForm.reset();
                updateValidationUI('');
            } catch (error) {
                messageEl.textContent = `Error: ${error.message}`;
                messageEl.classList.add('text-red-400');
            }
        });
    }

    userListBody.addEventListener('click', async (e) => {
        const targetButton = e.target.closest('button');
        if (!targetButton) return;
        const action = targetButton.dataset.action;
        const userId = targetButton.dataset.id;
        if (action === 'delete') {
            if (!window.confirm('Are you sure you want to delete this user?')) return;
            try {
                await fetch(`/api/users/${userId}`, { method: 'DELETE', headers: { 'Authorization': `Bearer ${token}` } });
                loadUsers();
            } catch { alert('Failed to delete user.'); }
        } else if (action === 'toggle-active' || action === 'toggle-admin') {
            const row = targetButton.closest('tr');
            const isActive = row.cells[1].textContent.trim() === 'Active';
            const isAdmin = row.cells[2].textContent.trim() === 'Admin';
            const updatePayload = action === 'toggle-active' ? { is_active: !isActive } : { is_admin: !isAdmin };
            try {
                await fetch(`/api/users/${userId}`, {
                    method: 'PUT',
                    headers: headers,
                    body: JSON.stringify(updatePayload)
                });
                loadUsers();
            } catch { alert('Failed to update user.'); }
        } else if (action === 'change-password') {
            modalUsername.textContent = targetButton.dataset.username;
            modalUserId.value = userId;
            adminModal.classList.remove('hidden');
        }
    });

    modalCancelBtn.addEventListener('click', () => {
        adminModal.classList.add('hidden');
        adminModalForm.reset();
        modalMessageEl.textContent = '';
    });

    adminModalForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const userId = modalUserId.value;
        const newPassword = modalNewPassword.value;
        modalMessageEl.textContent = '';
        modalMessageEl.classList.remove('text-red-400', 'text-green-400');
        if (!validatePassword(newPassword)) {
            modalMessageEl.textContent = 'Password does not meet requirements.';
            modalMessageEl.classList.add('text-red-400');
            return;
        }
        try {
            const response = await fetch(`/api/users/${userId}/password`, {
                method: 'PUT',
                headers: headers,
                body: JSON.stringify({ new_password: newPassword })
            });
            if (!response.ok) { throw new Error((await response.json()).detail || 'Failed to change password'); }
            modalMessageEl.textContent = 'Password changed successfully!';
            modalMessageEl.classList.add('text-green-400');
            adminModalForm.reset();
            setTimeout(() => {
                adminModal.classList.add('hidden');
                modalMessageEl.textContent = '';
            }, 2000);
        } catch (error) {
            modalMessageEl.textContent = `Error: ${error.message}`;
            modalMessageEl.classList.add('text-red-400');
        }
    });

    // --- Initial loads ---
    loadUsers();
    loadTemplates();

    const headerRow = document.createElement('div');
    headerRow.className = 'grid grid-cols-1 md:grid-cols-7 gap-2 items-center mb-2 text-sm font-semibold text-gray-400';
    headerRow.innerHTML = `
        <div class="md:col-span-2 px-2">Squad Name</div>
        <div class="px-2">Count</div>
        <div class="px-2">Player Pool</div>
        <div class="px-2">Squad Rules</div>
        <div class="px-2">Naming</div>
        <div class="px-2 text-center">Action</div>
    `;
    definitionsContainer.appendChild(headerRow);

    addDefinitionRow();
});
