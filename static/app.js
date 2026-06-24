/* ============================================================
   AutoCAD BOM Extractor – Application Logic
   ============================================================ */

(function () {
    'use strict';

    // ---- State ----
    let projectsList = [];
    let currentProject = null;
    let bomData = [];
    let filteredData = [];
    let activeFilter = null;
    let activeCategoryFilter = null;
    let sortColumn = null;
    let sortAsc = true;

    // ---- DOM Refs ----
    const projectWarningSection = document.getElementById('projectWarningSection');
    const uploadSection = document.getElementById('uploadSection');
    const uploadZone = document.getElementById('uploadZone');
    const fileInput = document.getElementById('fileInput');
    const browseBtn = document.getElementById('browseBtn');
    const processingSection = document.getElementById('processingSection');
    const processingText = document.getElementById('processingText');
    const progressFill = document.getElementById('progressFill');
    const resultsSection = document.getElementById('resultsSection');
    const errorSection = document.getElementById('errorSection');
    const errorText = document.getElementById('errorText');
    const statFiles = document.getElementById('statFiles');
    const statRows = document.getElementById('statRows');
    const statProjects = document.getElementById('statProjects');
    const searchInput = document.getElementById('searchInput');
    const filterChips = document.getElementById('filterChips');
    const categoryFilterChips = document.getElementById('categoryFilterChips');
    const tableBody = document.getElementById('tableBody');
    const emptySearch = document.getElementById('emptySearch');
    const exportCsvBtn = document.getElementById('exportCsvBtn');
    const exportJsonBtn = document.getElementById('exportJsonBtn');
    const newUploadBtn = document.getElementById('newUploadBtn');
    const clearDataBtn = document.getElementById('clearDataBtn');
    const retryBtn = document.getElementById('retryBtn');

    // Sidebar & Projects
    const projectList = document.getElementById('projectList');
    const newProjectBtn = document.getElementById('newProjectBtn');
    const warningCreateProjectBtn = document.getElementById('warningCreateProjectBtn');
    const subProjectsSection = document.getElementById('subProjectsSection');
    const categoriesSection = document.getElementById('categoriesSection');
    const activeProjectName = document.getElementById('activeProjectName');

    // Modal
    const projectModal = document.getElementById('projectModal');
    const closeModalBtn = document.getElementById('closeModalBtn');
    const cancelProjectBtn = document.getElementById('cancelProjectBtn');
    const saveProjectBtn = document.getElementById('saveProjectBtn');
    const newProjectName = document.getElementById('newProjectName');
    const modalError = document.getElementById('modalError');

    // ---- Section Visibility ----
    function showSection(section) {
        [projectWarningSection, uploadSection, processingSection, resultsSection, errorSection].forEach(s => {
            if (s) s.classList.add('hidden');
        });
        if (section) section.classList.remove('hidden');
    }

    // ---- Fetch and Populate Projects ----
    async function fetchProjects(selectDefaultName = null) {
        try {
            const response = await fetch('/api/projects');
            if (!response.ok) throw new Error('Failed to load projects list.');
            
            projectsList = await response.json();
            renderProjectsList();

            // Determine which project to select
            let projectToSelect = selectDefaultName;
            
            if (!projectToSelect) {
                const savedProject = localStorage.getItem('bom_extractor_current_project');
                if (savedProject && projectsList.some(p => p.name === savedProject)) {
                    projectToSelect = savedProject;
                } else if (projectsList.length > 0) {
                    projectToSelect = projectsList[0].name;
                }
            }

            if (projectToSelect && projectsList.some(p => p.name === projectToSelect)) {
                selectProject(projectToSelect);
            } else {
                currentProject = null;
                localStorage.removeItem('bom_extractor_current_project');
                activeProjectName.textContent = 'Select a Project';
                subProjectsSection.classList.add('hidden');
                categoriesSection.classList.add('hidden');
                showSection(projectWarningSection);
            }
        } catch (err) {
            console.error(err);
            showError('Database connection error. Could not retrieve project list.');
        }
    }

    function renderProjectsList() {
        projectList.innerHTML = '';
        if (projectsList.length === 0) {
            projectList.innerHTML = '<div class="project-item empty">No projects yet</div>';
            return;
        }

        projectsList.forEach(p => {
            const item = document.createElement('div');
            item.className = 'project-item';
            item.setAttribute('data-name', p.name);
            if (currentProject === p.name) {
                item.classList.add('active');
            }
            
            item.innerHTML = `
                <span>${esc(p.name)}</span>
                <div class="project-actions">
                    <span class="file-count">${p.total_files} file${p.total_files !== 1 ? 's' : ''}</span>
                    <button class="btn-delete-project" title="Delete Project">&times;</button>
                </div>
            `;
            
            item.addEventListener('click', () => {
                selectProject(p.name);
            });

            const delBtn = item.querySelector('.btn-delete-project');
            if (delBtn) {
                delBtn.addEventListener('click', async (e) => {
                    e.stopPropagation(); // Prevent project selection click
                    if (!confirm(`Are you sure you want to permanently delete project "${p.name}" and all its associated drawings and BOM items?`)) {
                        return;
                    }
                    
                    try {
                        const response = await fetch(`/api/projects?project=${encodeURIComponent(p.name)}`, {
                            method: 'DELETE'
                        });
                        
                        const result = await response.json();
                        if (!response.ok) {
                            throw new Error(result.detail || 'Failed to delete project.');
                        }
                        
                        let nextSelection = null;
                        if (currentProject === p.name) {
                            const otherProjects = projectsList.filter(proj => proj.name !== p.name);
                            if (otherProjects.length > 0) {
                                nextSelection = otherProjects[0].name;
                            }
                        } else {
                            nextSelection = currentProject;
                        }
                        
                        await fetchProjects(nextSelection);
                    } catch (err) {
                        alert(err.message);
                    }
                });
            }

            projectList.appendChild(item);
        });
    }

    function selectProject(projectName) {
        currentProject = projectName;
        localStorage.setItem('bom_extractor_current_project', projectName);
        
        // Update active class in sidebar
        document.querySelectorAll('.project-list .project-item').forEach(item => {
            if (item.getAttribute('data-name') === projectName) {
                item.classList.add('active');
            } else {
                item.classList.remove('active');
            }
        });

        activeProjectName.textContent = projectName;
        loadProjectData(projectName);
    }

    async function loadProjectData(projectName) {
        showSection(processingSection);
        processingText.textContent = `Loading project data for "${projectName}"...`;
        progressFill.style.width = '30%';

        try {
            const response = await fetch(`/api/bom?project=${encodeURIComponent(projectName)}`);
            progressFill.style.width = '80%';
            
            if (!response.ok) {
                throw new Error(`Server returned ${response.status}`);
            }

            const result = await response.json();
            progressFill.style.width = '100%';

            setTimeout(() => {
                if (result.status === 'success' && result.total_files_processed > 0) {
                    bomData = result.data || [];
                    filteredData = [...bomData];
                    
                    // Reset search and filters
                    searchInput.value = '';
                    activeFilter = null;
                    activeCategoryFilter = null;
                    sortColumn = null;
                    sortAsc = true;
                    
                    renderResults(result.total_files_processed);
                    subProjectsSection.classList.remove('hidden');
                    categoriesSection.classList.remove('hidden');
                    showSection(resultsSection);
                } else {
                    bomData = [];
                    filteredData = [];
                    subProjectsSection.classList.add('hidden');
                    categoriesSection.classList.add('hidden');
                    showSection(uploadSection);
                }
            }, 300);
        } catch (err) {
            showError(`Failed to load data for project "${projectName}": ${err.message}`);
        }
    }

    // ---- Project Creation Modal ----
    function openModal() {
        projectModal.classList.remove('hidden');
        newProjectName.focus();
        modalError.classList.add('hidden');
        newProjectName.value = '';
    }

    function closeModal() {
        projectModal.classList.add('hidden');
        newProjectName.value = '';
        modalError.classList.add('hidden');
    }

    async function handleCreateProject() {
        const name = newProjectName.value.trim();
        if (!name) return;

        try {
            const response = await fetch('/api/projects', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ name })
            });

            const result = await response.json();
            if (!response.ok) {
                throw new Error(result.detail || 'Failed to create project.');
            }

            closeModal();
            // Reload projects and select the newly created project
            await fetchProjects(name);
        } catch (err) {
            modalError.textContent = err.message;
            modalError.classList.remove('hidden');
        }
    }

    // Modal Event Bindings
    newProjectBtn.addEventListener('click', openModal);
    warningCreateProjectBtn.addEventListener('click', openModal);
    closeModalBtn.addEventListener('click', closeModal);
    cancelProjectBtn.addEventListener('click', closeModal);
    saveProjectBtn.addEventListener('click', handleCreateProject);
    
    newProjectName.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
            e.preventDefault();
            handleCreateProject();
        } else if (e.key === 'Escape') {
            closeModal();
        }
    });

    // Close modal on click outside content
    projectModal.addEventListener('click', (e) => {
        if (e.target === projectModal) closeModal();
    });

    // ---- Upload Handlers ----
    function handleFile(file) {
        if (!file) return;

        if (!currentProject) {
            alert('Please select or create a project first.');
            return;
        }

        if (!file.name.toLowerCase().endsWith('.zip')) {
            showError('Please upload a .zip file containing AutoCAD .dwg or .dxf drawings.');
            return;
        }

        uploadFile(file);
    }

    // Drag and drop
    uploadZone.addEventListener('dragover', (e) => {
        e.preventDefault();
        uploadZone.classList.add('drag-over');
    });

    uploadZone.addEventListener('dragleave', () => {
        uploadZone.classList.remove('drag-over');
    });

    uploadZone.addEventListener('drop', (e) => {
        e.preventDefault();
        uploadZone.classList.remove('drag-over');
        const file = e.dataTransfer.files[0];
        handleFile(file);
    });

    // Click to browse
    uploadZone.addEventListener('click', (e) => {
        if (e.target === browseBtn || browseBtn.contains(e.target)) return;
        fileInput.click();
    });

    browseBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        fileInput.click();
    });

    fileInput.addEventListener('change', () => {
        handleFile(fileInput.files[0]);
        fileInput.value = '';
    });

    // Retry / new upload
    retryBtn.addEventListener('click', () => {
        if (currentProject) {
            showSection(uploadSection);
        } else {
            showSection(projectWarningSection);
        }
    });
    
    newUploadBtn.addEventListener('click', () => {
        if (currentProject) {
            showSection(uploadSection);
        }
    });

    clearDataBtn.addEventListener('click', async () => {
        if (!currentProject) return;
        if (!confirm(`Are you sure you want to permanently clear all stored BOM data for project "${currentProject}"?`)) return;
        
        try {
            const response = await fetch(`/api/bom?project=${encodeURIComponent(currentProject)}`, {
                method: 'DELETE',
            });
            if (!response.ok) throw new Error('Database clear request failed.');
            
            // Reload projects list to update count in sidebar
            await fetchProjects(currentProject);
        } catch (e) {
            console.error('Failed to clear BOM database', e);
            showError('Failed to clear stored BOM data.');
        }
    });

    // ---- API Upload Call ----
    async function uploadFile(file) {
        showSection(processingSection);
        processingText.textContent = 'Uploading ZIP file...';
        progressFill.style.width = '15%';

        const formData = new FormData();
        formData.append('file', file);

        try {
            // Simulate progress state transitions
            setTimeout(() => {
                if (currentProject) {
                    processingText.textContent = 'Converting DWG → DXF and extracting block attributes...';
                    progressFill.style.width = '45%';
                }
            }, 800);

            setTimeout(() => {
                if (currentProject) {
                    processingText.textContent = 'Building BOM database table...';
                    progressFill.style.width = '75%';
                }
            }, 1800);

            const response = await fetch(`/api/extract?project=${encodeURIComponent(currentProject)}`, {
                method: 'POST',
                body: formData,
            });

            progressFill.style.width = '100%';

            if (!response.ok) {
                const err = await response.json().catch(() => ({}));
                throw new Error(err.detail || `Server returned ${response.status}`);
            }

            const result = await response.json();

            if (result.status !== 'success') {
                throw new Error(result.detail || 'Extraction failed.');
            }

            // Short delay for the progress bar animation to complete
            setTimeout(async () => {
                // Refresh project list to update file count in sidebar
                await fetchProjects(currentProject);
            }, 400);

        } catch (err) {
            showError(err.message);
        }
    }

    // ---- Error Display ----
    function showError(message) {
        errorText.textContent = message;
        showSection(errorSection);
    }

    // ---- Render Results ----
    function renderResults(totalFiles) {
        // Stats
        animateCounter(statFiles, totalFiles);
        animateCounter(statRows, bomData.length);

        const subProjects = [...new Set(bomData.map(r => r.sub_project))];
        animateCounter(statProjects, subProjects.length);

        // Filter chips
        renderFilterChips(subProjects);
        renderCategoryFilterChips();

        // Table
        renderTable();
    }

    function animateCounter(el, target) {
        let current = 0;
        const step = Math.max(1, Math.ceil(target / 15));
        const timer = setInterval(() => {
            current += step;
            if (current >= target) {
                current = target;
                clearInterval(timer);
            }
            el.textContent = current;
        }, 25);
    }

    // ---- Filter Chips in Sidebar ----
    function renderFilterChips(subProjects) {
        filterChips.innerHTML = '';

        // "All Sub-Projects" is a simple chip button
        const allChip = document.createElement('button');
        allChip.className = 'filter-chip';
        allChip.textContent = 'All Sub-Projects';
        if (activeFilter === null) {
            allChip.classList.add('active');
        }
        allChip.addEventListener('click', () => {
            activeFilter = null;
            // Clear active classes from all chips/wrappers
            filterChips.querySelectorAll('.subproject-item, .filter-chip').forEach(el => el.classList.remove('active'));
            allChip.classList.add('active');
            applyFilters();
        });
        filterChips.appendChild(allChip);

        // Individual sub-projects
        subProjects.forEach(sp => {
            const item = document.createElement('div');
            item.className = 'subproject-item';
            if (activeFilter === sp) {
                item.classList.add('active');
            }

            item.innerHTML = `
                <button class="filter-chip">${esc(sp)}</button>
                <button class="btn-delete-subproject" title="Delete Sub-Project">&times;</button>
            `;

            // Click subproject to filter
            const chipBtn = item.querySelector('.filter-chip');
            chipBtn.addEventListener('click', () => {
                activeFilter = sp;
                filterChips.querySelectorAll('.subproject-item, .filter-chip').forEach(el => el.classList.remove('active'));
                item.classList.add('active');
                applyFilters();
            });

            // Click delete to clear sub-project data
            const delBtn = item.querySelector('.btn-delete-subproject');
            delBtn.addEventListener('click', async (e) => {
                e.stopPropagation(); // Avoid triggering filter chip click
                if (!confirm(`Are you sure you want to permanently delete sub-project "${sp}" and all its drawings and BOM data from project "${currentProject}"?`)) {
                    return;
                }

                try {
                    const response = await fetch(`/api/bom?project=${encodeURIComponent(currentProject)}&sub_project=${encodeURIComponent(sp)}`, {
                        method: 'DELETE'
                    });

                    const result = await response.json();
                    if (!response.ok) {
                        throw new Error(result.detail || 'Failed to delete sub-project.');
                    }

                    // Reset activeFilter if we deleted the currently filtered sub-project
                    if (activeFilter === sp) {
                        activeFilter = null;
                    }

                    // Reload project list to update total files count in sidebar, and re-load project data
                    await fetchProjects(currentProject);
                } catch (err) {
                    alert(err.message);
                }
            });

            filterChips.appendChild(item);
        });
    }

    function renderCategoryFilterChips() {
        categoryFilterChips.innerHTML = '';

        const categories = ['All Categories', 'Pipe', 'Fitting', 'Gasket', 'Hardware', 'Other'];
        categories.forEach(cat => {
            const chip = document.createElement('button');
            chip.className = 'filter-chip';
            
            const isAll = cat === 'All Categories';
            const isActive = (isAll && !activeCategoryFilter) || (!isAll && activeCategoryFilter === cat);
            
            if (isActive) {
                chip.classList.add('active');
            }
            
            chip.textContent = cat;
            chip.addEventListener('click', () => {
                activeCategoryFilter = isAll ? null : cat;
                categoryFilterChips.querySelectorAll('.filter-chip').forEach(c => c.classList.remove('active'));
                chip.classList.add('active');
                applyFilters();
            });
            categoryFilterChips.appendChild(chip);
        });
    }

    // ---- Search & Filter ----
    searchInput.addEventListener('input', () => applyFilters());

    function applyFilters() {
        const query = searchInput.value.toLowerCase().trim();

        filteredData = bomData.filter(row => {
            if (activeFilter && row.sub_project !== activeFilter) return false;
            if (activeCategoryFilter && row.category !== activeCategoryFilter) return false;
            if (query) {
                const text = [
                    row.sub_project, row.drawing, row.category, row.pno,
                    row.description, row.size, row.material,
                    row.standard
                ].join(' ').toLowerCase();
                return text.includes(query);
            }
            return true;
        });

        if (sortColumn) {
            sortData(sortColumn, false);
        } else {
            renderTable();
        }
    }

    // ---- Sorting ----
    document.querySelectorAll('.data-table th[data-sort]').forEach(th => {
        th.addEventListener('click', () => {
            const col = th.getAttribute('data-sort');
            sortData(col, true);
        });
    });

    function sortData(column, toggle) {
        if (toggle) {
            if (sortColumn === column) {
                sortAsc = !sortAsc;
            } else {
                sortColumn = column;
                sortAsc = true;
            }
        }

        filteredData.sort((a, b) => {
            let va = a[column];
            let vb = b[column];

            // Handle numeric / quantity sorting naturally
            if ((column === 'qty' || column === 'weight')) {
                const numA = va != null ? Number(va) : -Infinity;
                const numB = vb != null ? Number(vb) : -Infinity;
                return sortAsc ? numA - numB : numB - numA;
            }

            // Fallback for strings
            const strA = va != null ? String(va).toLowerCase() : '';
            const strB = vb != null ? String(vb).toLowerCase() : '';

            // Natural sort helper for parts with numbers (like PNo)
            if (column === 'pno' || column === 'sub_project' || column === 'drawing') {
                return sortAsc 
                    ? strA.localeCompare(strB, undefined, { numeric: true, sensitivity: 'base' })
                    : strB.localeCompare(strA, undefined, { numeric: true, sensitivity: 'base' });
            }

            if (strA < strB) return sortAsc ? -1 : 1;
            if (strA > strB) return sortAsc ? 1 : -1;
            return 0;
        });

        // Update header sort indicators
        document.querySelectorAll('.data-table th').forEach(th => {
            th.classList.remove('sorted');
            const icon = th.querySelector('.sort-icon');
            if (icon) icon.textContent = '↕';
        });

        const activeHeader = document.querySelector(`.data-table th[data-sort="${sortColumn}"]`);
        if (activeHeader) {
            activeHeader.classList.add('sorted');
            const icon = activeHeader.querySelector('.sort-icon');
            if (icon) icon.textContent = sortAsc ? '↑' : '↓';
        }

        renderTable();
    }

    // ---- Table Rendering ----
    function renderTable() {
        tableBody.innerHTML = '';

        if (filteredData.length === 0) {
            emptySearch.classList.remove('hidden');
            document.querySelector('.table-container').classList.add('hidden');
            return;
        }

        emptySearch.classList.add('hidden');
        document.querySelector('.table-container').classList.remove('hidden');

        filteredData.forEach((row, i) => {
            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td>${esc(row.sub_project)}</td>
                <td>${esc(row.drawing)}</td>
                <td>
                    <span class="badge-category badge-${(row.category || 'Other').toLowerCase()}">
                        ${esc(row.category || 'Other')}
                    </span>
                </td>
                <td>${esc(row.pno)}</td>
                <td title="${esc(row.description)}">${esc(row.description)}</td>
                <td title="${esc(row.size)}">${esc(row.size)}</td>
                <td>${esc(row.material)}</td>
                <td>${esc(row.standard)}</td>
                <td class="cell-qty">${row.qty != null ? row.qty : '—'}</td>
                <td class="cell-qty-unit">${row.qty_unit ? esc(row.qty_unit) : '—'}</td>
                <td class="cell-weight">${row.weight != null ? row.weight : '—'}</td>
                <td class="cell-weight-unit">${row.weight_unit ? esc(row.weight_unit) : '—'}</td>
            `;
            tableBody.appendChild(tr);
        });
    }

    function esc(str) {
        if (str == null) return '';
        const div = document.createElement('div');
        div.textContent = String(str);
        return div.innerHTML;
    }

    // ---- Export CSV ----
    exportCsvBtn.addEventListener('click', () => {
        if (filteredData.length === 0) return;
        
        const headers = ['Sub-Project', 'Drawing', 'Category', 'P.No', 'Description', 'Size', 'Material', 'Dim. Standard', 'Qty', 'Qty Unit', 'Weight', 'Weight Unit'];
        const rows = filteredData.map(r => [
            r.sub_project, r.drawing, r.category, r.pno, r.description,
            r.size, r.material, r.standard ?? '',
            r.qty ?? '', r.qty_unit ?? '',
            r.weight ?? '', r.weight_unit ?? ''
        ]);

        let csv = headers.join(',') + '\n';
        rows.forEach(row => {
            csv += row.map(cell => `"${String(cell).replace(/"/g, '""')}"`).join(',') + '\n';
        });

        const defaultFileName = currentProject ? `${currentProject.toLowerCase().replace(/[^a-z0-9]/g, '_')}_bom.csv` : 'bom_data.csv';
        downloadFile(defaultFileName, csv, 'text/csv');
    });

    // ---- Export JSON ----
    exportJsonBtn.addEventListener('click', () => {
        if (filteredData.length === 0) return;
        
        const json = JSON.stringify({ data: filteredData }, null, 2);
        const defaultFileName = currentProject ? `${currentProject.toLowerCase().replace(/[^a-z0-9]/g, '_')}_bom.json` : 'bom_data.json';
        downloadFile(defaultFileName, json, 'application/json');
    });

    function downloadFile(name, content, type) {
        const blob = new Blob([content], { type });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = name;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
    }

    // ---- Init ----
    fetchProjects();

})();
