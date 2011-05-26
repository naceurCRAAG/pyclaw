#!/usr/bin/env python
# encoding: utf-8
r"""
Module containing SharpClaw solvers for PyClaw/PetClaw

#  File:        sharpclaw.py
#  Created:     2010-03-20
#  Author:      David Ketcheson
"""
# ============================================================================
#      Copyright (C) 2010 David I. Ketcheson <david.ketcheson@kaust.edu.sa>
#
#  Distributed under the terms of the Berkeley Software Distribution (BSD) 
#  license
#                     http://www.opensource.org/licenses/
# ============================================================================

# Solver superclass
from pyclaw.evolve.solver import Solver, CFLError

# Reconstructor
try:
    # load c-based WENO reconstructor (PyWENO)
    from pyclaw.evolve import reconstruct as recon
except:
    # load old WENO5 reconstructor
    from pyclaw.evolve import recon


def start_step(solver,grid,rk_stage):
    r"""
    Dummy routine called before each step
    
    Replace this routine if you want to do something before each time step.
    """
    pass

def src(solver,grid,q,t):
    r"""
    Dummy routine called to calculate a source term
    
    Replace this routine if you want to include a source term.
    """
    pass

 
class RKStage(object):
    """
    A single Runge-Kutta stage.
    Here we have assumed the aux array is time-independent.
    Otherwise we would need to keep a copy of it with each RK stage.
    """
    def __init__(self,grid):
        import numpy as np

        self.q=np.zeros(grid.q.shape)
        self.t=grid.t


class SharpClawSolver(Solver):
    r""""""
    
    # ========================================================================
    #   Initialization routines
    # ========================================================================
    def __init__(self, data=None):
        r"""
        Here we just set the flag for using Python or Fortran kernels.
        """
        
        # Required attributes for this solver
        for attr in ['mthlim','start_step','lim_type','time_integrator',
                     'char_decomp','src_term','aux_time_dep','mwaves']:
            self._required_attrs.append(attr)
        
        # Defaults for required attributes
        self._default_attr_values['mthlim'] = [1]
        self._default_attr_values['start_step'] = start_step
        self._default_attr_values['lim_type'] = 2
        self._default_attr_values['time_integrator'] = 'SSP33'
        self._default_attr_values['char_decomp'] = 0
        self._default_attr_values['tfluct_solver'] = False
        self._default_attr_values['aux_time_dep'] = False
        self._default_attr_values['src_term'] = False
        self._default_attr_values['kernel_language'] = 'Fortran'
        self._default_attr_values['mbc'] = 3
        self._default_attr_values['fwave'] = False
        
        # Call general initialization function
        super(SharpClawSolver,self).__init__(data)
        
    # ========== Time stepping routines ======================================
    def step(self,solutions):
        """Evolve q over one time step.

        Takes the appropriate times steps to reach tend.  This is done based 
        on the current solution attributes set in the object.

        Arguments:
          tend - Target time step to reach
        """
        from pyclaw.solution import Solution
        # Grid we will be working on
        grid = solutions['n'].grids[0]

        try:
            if self.time_integrator=='Euler':
                deltaq=self.dq(grid,grid)
                grid.q+=deltaq
            elif self.time_integrator=='SSP33':
                deltaq=self.dq(grid,grid)
                self.rk_stages[0].q=grid.q+deltaq
                self.rk_stages[0].t =grid.t+self.dt
                deltaq=self.dq(grid,self.rk_stages[0])
                self.rk_stages[0].q= 0.75*grid.q + 0.25*(self.rk_stages[0].q+deltaq)
                self.rk_stages[0].t = grid.t+0.5*self.dt
                deltaq=self.dq(grid,self.rk_stages[0])
                grid.q = 1./3.*grid.q + 2./3.*(self.rk_stages[0].q+deltaq)
            else:
                raise Exception('Unrecognized time integrator')
        except CFLError:
            return False

        
    def dq(self,grid,rk_stage):
        """
        Evaluate dq/dt * (delta t)
        """

        start_step(self,grid,rk_stage)

        q = self.qbc(grid,rk_stage)

        deltaq = self.dq_homogeneous(grid,q,rk_stage.t)

        # Check here if we violated the CFL condition, if we did, return 
        # immediately to evolve_to_time and let it deal with picking a new
        # dt
        self.communicateCFL()
        if self.cfl >= self.cfl_max:
            raise CFLError('cfl_max exceeded')

        # Godunov Splitting -- really the source term should be called inside rkstep
        if self.src_term == 1:
            deltaq+=self.src(grid,q,rk_stage.t)

        return deltaq

    def dq_homogeneous(grid,q,t):
        raise NotImplementedError('You must subclass SharpClawSolver.')

    def list_riemann_solvers(self):
        r"""
        List available Riemann solvers 
        
        This routine returns a list of available Riemann solvers which is
        constructed in the Riemann solver package (:ref:`pyclaw_rp`).  In this 
        case it lists all Riemann solvers.
        
        :Output:
         - (list) - List of Riemann solver names valid to be used with
           :meth:`set_riemann_solver`
        
        .. note::
            These Riemann solvers are currently only accessible to the python 
            time stepping routines.
        """
        rp_solver_list = []
        
        # Construct list from each dimension list
        for rp_solver in rp_solver_list_1d:
            rp_solver_list.append('%s_1d' % rp_solver)
        for rp_solver in rp_solver_list_2d:
            rp_solver_list.append('%s_2d' % rp_solver)
        for rp_solver in rp_solver_list_3d:
            rp_solver_list.append('%s_3d' % rp_solver)
        
        return rp_solver_list
    
    def set_riemann_solver(self,solver_name):
        r"""
        Assigns the library solver solver_name as the Riemann solver.
        
        :Input:
         - *solver_name* - (string) Name of the solver to be used, raises a 
           NameError if the solver does not exist.
        """
        raise Exception("Cannot set a Riemann solver with this class," +
                                        " use one of the derived classes.")
         
    def dqdt(self,grid,rk_stage):
        """
        Evaluate dq/dt.  This routine is used for implicit time stepping.
        """

        q = self.qbc(grid,rk_stage.q,rk_stage.t)

        self.dt = 1
        deltaq = self.dq_homogeneous(grid,q,rk_stage.t)

        # Godunov Splitting -- really the source term should be called inside rkstep
        if self.src_term == 1:
            deltaq+=self.src(grid,q,rk_stage.t)

        return deltaq.flatten('f')


    def set_fortran_parameters(self,grid,clawparams,workspace,reconstruct):
        """
        Set parameters for Fortran modules used by SharpClaw.
        The modules should be imported and passed as arguments to this function.

        """
        clawparams.ndim          = grid.ndim
        clawparams.lim_type      = self.lim_type
        clawparams.char_decomp   = self.char_decomp
        clawparams.tfluct_solver = self.tfluct_solver
        clawparams.fwave         = self.fwave
        if grid.capa is not None:
            clawparams.mcapa         = 1
        else:
            clawparams.mcapa         = 0

        clawparams.mwaves        = self.mwaves
        clawparams.alloc_clawparams()
        for idim in range(grid.ndim):
            clawparams.xlower[idim]=grid.dimensions[idim].lower
            clawparams.xupper[idim]=grid.dimensions[idim].upper
        clawparams.dx       =grid.d
        clawparams.mthlim   =self.mthlim

        maxnx = max(grid.q.shape[1:])+2*self.mbc
        workspace.alloc_workspace(maxnx,self.mbc,grid.meqn,self.mwaves,self.char_decomp)
        reconstruct.alloc_recon_workspace(maxnx,self.mbc,grid.meqn,self.mwaves,
                                            clawparams.lim_type,clawparams.char_decomp)



# ========================================================================
class SharpClawSolver1D(SharpClawSolver):
# ========================================================================
    """SharpClaw evolution routine in 1D
    
    This class represents the 1d SharpClaw solver.  Note that there are 
    routines here for interfacing with the fortran time stepping routines and
    the python time stepping routines.  The ones used are dependent on the 
    argument given to the initialization of the solver (defaults to fortran).
    
    """
    def __init__(self, data=None):
        r"""
        Create 1d SharpClaw solver
        
        See :class:`ClawSolver1D` for more info.
        """   
        
        # Add the functions as required attributes
        self._required_attrs.append('rp')
        self._default_attr_values['rp'] = None
        
        # Import Riemann solvers
        exec('import riemann',globals())
            
        super(SharpClawSolver1D,self).__init__(data)


    def setup(self,solutions):
        """
        Allocate RK stage arrays and fortran routine work arrays.
        """
        if self.time_integrator == 'Euler': nregisters=1
        elif self.time_integrator == 'SSP33': nregisters=2
 
        grid = solutions['n'].grids[0]
        self.rk_stages = []
        for i in range(nregisters-1):
            self.rk_stages.append(RKStage(grid))

        #Set up mthlim array
        if not isinstance(self.mthlim,list): self.mthlim=[self.mthlim]
        if len(self.mthlim)==1: self.mthlim = self.mthlim * self.mwaves
        if len(self.mthlim)!=self.mwaves:
            raise Exception('Length of solver.mthlim is not 1 nor is it equal to solver.mwaves')
 
        if self.kernel_language=='Fortran':
            from sharpclaw1 import clawparams, workspace, reconstruct
            import sharpclaw1
            grid.set_cparam(sharpclaw1)
            self.set_fortran_parameters(grid,clawparams,workspace,reconstruct)

    def teardown(self):
        if self.kernel_language=='Fortran':
            from sharpclaw1 import clawparams, workspace, reconstruct
            clawparams.dealloc_clawparams()
            workspace.dealloc_workspace(self.char_decomp)
            reconstruct.dealloc_recon_workspace(clawparams.lim_type,clawparams.char_decomp)

    # ========== Riemann solver library routines =============================   
    def set_riemann_solver(self,solver_name):
        r"""
        Assigns the library solver solver_name as the Riemann solver.
        
        :Input:
         - *solver_name* - (string) Name of the solver to be used, raises a 
           ``NameError`` if the solver does not exist.
        """
        import logging
        if solver_name in riemann.rp_solver_list_1d:
            self.rp = getattr(riemann,'rp_%s_1d' % solver_name)
        else:
            logger = logging.getLogger('solver')
            error_msg = 'Could not find Riemann solver with name %s' % solver_name
            logger.warning(error_msg)
            raise NameError(error_msg)


    def dq_homogeneous(self,grid,q, t):
        """Compute dq/dt * (delta t) for the homogeneous hyperbolic system

        Note that the capa array, if present, should be located in the aux
        variable.

        Indexing works like this:  here mbc=2 as an example
         0     1     2     3     4     mx+mbc-2     mx+mbc      mx+mbc+2
                     |                        mx+mbc-1 |  mx+mbc+1
         |     |     |     |     |   ...   |     |     |     |     |
            0     1  |  2     3            mx+mbc-2    |mx+mbc       
                                                  mx+mbc-1   mx+mbc+1

        The top indices represent the values that are located on the grid
        cell boundaries such as waves, s and other Riemann problem values, 
        the bottom for the cell centered values such as q.  In particular
        the ith grid cell boundary has the following related information:
                          i-1         i         i+1
                           |          |          |
                           |   i-1    |     i    |
                           |          |          |
        Again, grid cell boundary quantities are at the top, cell centered
        values are in the cell.

        """
    
        import numpy as np

        dq = np.zeros(q.shape)

        # Note that q is passed in with ghost cells attached
        mx = q.shape[1]-2*self.mbc

        ixy=1
        aux=grid.aux
        if(aux == None): aux = np.zeros( (grid.maux,mx+2*self.mbc) )

        if self.kernel_language=='Fortran':
            from sharpclaw1 import flux1
            dq,self.cfl=flux1(q,dq,aux,self.dt,t,ixy,mx,self.mbc,mx)

        elif self.kernel_language=='Python':

            dtdx = np.zeros( (mx+2*self.mbc) )

            # Find local value for dt/dx
            if grid.capa is not None:
                dtdx = self.dt / (grid.d[0] * grid.capa)
            else:
                dtdx += self.dt/grid.d[0]
 
            if aux is not None:
                aux_l=aux[:,:-1]
                aux_r=aux[:,1: ]
            else:
                aux_l = None
                aux_r = None

            #Reconstruct (wave reconstruction uses a Riemann solve)
            if self.lim_type==-1: #1st-order Godunov
                ql=q; qr=q;
            elif self.lim_type==0: #Unlimited reconstruction
                raise NotImplementedError('Unlimited reconstruction not implemented')
            elif self.lim_type==1: #TVD Reconstruction
                raise NotImplementedError('TVD reconstruction not implemented')
            elif self.lim_type==2: #WENO Reconstruction
                if self.char_decomp==0: #No characteristic decomposition
                    ql,qr=recon.weno(5,q)
                elif self.char_decomp==1: #Wave-based reconstruction
                    q_l=q[:,:-1]
                    q_r=q[:,1: ]
                    wave,s,amdq,apdq = self.rp(q_l,q_r,aux_l,aux_r,grid.aux_global)
                    ql,qr=recon.weno5_wave(q,wave,s)
                elif self.char_decomp==2: #Characteristic-wise reconstruction
                    raise NotImplementedError

            # Solve Riemann problem at each interface
            q_l=qr[:,:-1]
            q_r=ql[:,1: ]
            wave,s,amdq,apdq = self.rp(q_l,q_r,aux_l,aux_r,grid.aux_global)

            # Loop limits for local potion of grid
            LL = self.mbc - 1
            UL = grid.n[0] + self.mbc + 1

            # Compute maximum wave speed
            self.cfl = 0.0
            for mw in xrange(self.mwaves):
                smax1 = np.max(dtdx[LL:UL]*s[mw,LL-1:UL-1])
                smax2 = np.max(-dtdx[LL-1:UL-1]*s[mw,LL-1:UL-1])
                self.cfl = max(self.cfl,smax1,smax2)

            #Find total fluctuation within each cell
            wave,s,amdq2,apdq2 = self.rp(ql,qr,grid.aux,grid.aux,grid.aux_global)

            # Compute dq
            for m in xrange(grid.meqn):
                dq[m,LL:UL] = -dtdx[LL:UL]*(amdq[m,LL:UL] + apdq[m,LL-1:UL-1] \
                                + apdq2[m,LL:UL] + amdq2[m,LL:UL])

        else: raise Exception('Unrecognized value of solver.kernel_language.')
        
        return dq[:,self.mbc:-self.mbc]
    
    def dqdt(self,grid,rk_stage):
        """
        Evaluate dq/dt.  This routine is used for implicit time stepping.
        """

        q = self.qbc(grid,rk_stage.q,rk_stage.t)

        self.dt = 1
        deltaq = self.dq_homogeneous(grid,q,rk_stage.t)

        # Godunov Splitting -- really the source term should be called inside rkstep
        if self.src_term == 1:
            deltaq+=self.src(grid,q,rk_stage.t)

        return deltaq.flatten('f')


# ========================================================================
class SharpClawSolver2D(SharpClawSolver):
# ========================================================================
    """SharpClaw evolution routine in 2D
    
    This class represents the 2D SharpClaw solver.  Note that there are 
    routines here for interfacing with the fortran time stepping routines only.
    """
    def __init__(self, data=None):
        r"""
        Create 2D SharpClaw solver
        
        See :class:`SharpClawSolver2D` for more info.
        """   
        
        super(SharpClawSolver2D,self).__init__(data)


    def setup(self,solutions):
        """
        Allocate RK stage arrays and fortran routine work arrays.
        """
        if self.time_integrator == 'Euler': nregisters=1
        elif self.time_integrator == 'SSP33': nregisters=2
 
        grid = solutions['n'].grids[0]
        self.rk_stages = []
        for i in range(nregisters-1):
            self.rk_stages.append(RKStage(grid))

        #Set up mthlim array
        if not isinstance(self.mthlim,list): self.mthlim=[self.mthlim]
        if len(self.mthlim)==1: self.mthlim = self.mthlim * self.mwaves
        if len(self.mthlim)!=self.mwaves:
            raise Exception('Length of solver.mthlim is not 1 nor is it equal to solver.mwaves')
 
        if self.kernel_language=='Fortran':
            from sharpclaw2 import clawparams, workspace, reconstruct
            import sharpclaw2
            grid.set_cparam(sharpclaw2)
            self.set_fortran_parameters(grid,clawparams,workspace,reconstruct)

    def teardown(self):
        if self.kernel_language=='Fortran':
            from sharpclaw2 import clawparams, workspace, reconstruct
            workspace.dealloc_workspace(self.char_decomp)
            reconstruct.dealloc_recon_workspace(clawparams.lim_type,clawparams.char_decomp)
            clawparams.dealloc_clawparams()

    def dq_homogeneous(self,grid,q, t):
        """Compute dq/dt * (delta t) for the homogeneous hyperbolic system

        Note that the capa array, if present, should be located in the aux
        variable.

        Indexing works like this:  here mbc=2 as an example
         0     1     2     3     4     mx+mbc-2     mx+mbc      mx+mbc+2
                     |                        mx+mbc-1 |  mx+mbc+1
         |     |     |     |     |   ...   |     |     |     |     |
            0     1  |  2     3            mx+mbc-2    |mx+mbc       
                                                  mx+mbc-1   mx+mbc+1

        The top indices represent the values that are located on the grid
        cell boundaries such as waves, s and other Riemann problem values, 
        the bottom for the cell centered values such as q.  In particular
        the ith grid cell boundary has the following related information:
                          i-1         i         i+1
                           |          |          |
                           |   i-1    |     i    |
                           |          |          |
        Again, grid cell boundary quantities are at the top, cell centered
        values are in the cell.

        """
    
        import numpy as np

        dq = np.zeros(q.shape, order='F')

        mbc=self.mbc
        mx=q.shape[1]-2*mbc
        my=q.shape[2]-2*mbc
        maxm = max(mx,my)

        q1d  = np.zeros((grid.meqn,maxm+2*mbc), order='F')
        dq1d = np.zeros((grid.meqn,maxm+2*mbc), order='F')

        aux=grid.aux
        if(aux == None): 
            aux = np.zeros( (grid.maux,mx+2*mbc,my+2*mbc), order='F' )

        if self.kernel_language=='Fortran':
            from sharpclaw2 import flux2
            dq,self.cfl=flux2(q,dq,q1d,dq1d,aux,self.dt,t,mbc,maxm,mx,my)

        else: raise Exception('Only Fortran kernels are supported in 2D.')

        return dq[:,mbc:-mbc,mbc:-mbc]
