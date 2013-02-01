

#!/bin/bash

export CFLAGS="-O3 -s"
export CXXFLAGS="-O3 -s"
export OPT="-O3 -s"
export PATH=$OPENSHIFT_DATA_DIR/bin:$PATH

cd $OPENSHIFT_TMP_DIR

wget http://python.org/ftp/python/2.7.3/Python-2.7.3.tar.bz2
tar jxf Python-2.7.3.tar.bz2
cd Python-2.7.3

./configure --prefix=$OPENSHIFT_DATA_DIR
make
make install

$OPENSHIFT_DATA_DIR/bin/python -V

cd $OPENSHIFT_TMP_DIR
rm -rf ./Python-2.7.3*

wget http://pypi.python.org/packages/source/s/setuptools/setuptools-0.6c11.tar.gz
tar zxf setuptools-0.6c11.tar.gz
cd setuptools-0.6c11
$OPENSHIFT_DATA_DIR/bin/python setup.py install

cd $OPENSHIFT_TMP_DIR
rm -rf ./setuptools-0.6c11*

wget http://pypi.python.org/packages/source/p/pip/pip-1.1.tar.gz
tar zxf pip-1.1.tar.gz
cd pip-1.1
$OPENSHIFT_DATA_DIR/bin/python setup.py install

cd $OPENSHIFT_TMP_DIR
rm -rf ./pip-1.1*

$OPENSHIFT_DATA_DIR/bin/pip install virtualenv

echo "Done setting up Python 2.7"
touch $OPENSHIFT_DATA_DIR/setup_completed
